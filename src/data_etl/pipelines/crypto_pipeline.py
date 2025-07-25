"""
Crypto data pipeline for Exodus v2025.
Demonstrates end-to-end data flow: download -> validate -> split -> store.
"""

import os
import sys
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import pandas as pd
from pathlib import Path

from data_etl.providers.crypto.bybit_downloader import BybitDownloader
from data_etl.processing.enhanced_metadata_manager import EnhancedMetadataManager
from data_etl.validation.simple_validator import SimpleDataValidator
from data_etl.processing.data_splitter import DataSplitter
from data_etl.storage.timeseries_db import TimeSeriesDB
from data_etl.storage.metadata_db import MetadataDB
from data_etl.storage.postgresql_storage import store_processed_data_to_postgresql, DEFAULT_CONNECTION_PARAMS

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CryptoPipeline:
    """
    Complete crypto data pipeline integrating all data processing components.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the pipeline with configuration.
        
        Args:
            config: Configuration dictionary containing:
                - data_dir: Data directory path
                - db_config: Database configuration
                - providers: Provider configurations
                - validation_config: Validation parameters
        """
        self.config = config
        self.data_dir = Path(config['data_dir'])
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self.metadata_manager = EnhancedMetadataManager(self.data_dir)
        self.validator = SimpleDataValidator(config.get('validation_config', {}))
        self.splitter = DataSplitter()
        
        # Database connections
        self.db_config = config['db_config']
        self.timeseries_db = None
        self.metadata_db = None
        
        # Provider instances
        self.providers = {}
        self._init_providers()
        
    def _init_providers(self) -> None:
        """Initialize data provider instances."""
        provider_configs = self.config.get('providers', {})
        
        # Initialize Bybit provider (works with or without API keys for public endpoints)
        bybit_config = provider_configs.get('bybit', {})
        self.providers['bybit'] = BybitDownloader(
            api_key=bybit_config.get('api_key'),
            api_secret=bybit_config.get('api_secret'),
            testnet=bybit_config.get('testnet', False)
        )
        logger.info("Bybit provider initialized (using public endpoints)")
    
    def _init_databases(self) -> None:
        """Initialize database connections."""
        try:
            self.timeseries_db = TimeSeriesDB(self.db_config)
            self.timeseries_db.connect()
            self.timeseries_db.create_hypertable()
            
            self.metadata_db = MetadataDB(self.db_config)
            self.metadata_db.connect()
            self.metadata_db.create_tables()
            
            logger.info("Database connections initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize databases: {e}")
            raise
    
    def _cleanup_databases(self) -> None:
        """Clean up database connections."""
        if self.timeseries_db:
            self.timeseries_db.disconnect()
        if self.metadata_db:
            self.metadata_db.disconnect()
    
    def download_data(self, provider: str, symbol: str, timeframe: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """
        Download data from specified provider.
        
        Args:
            provider: Provider name (e.g., 'bybit')
            symbol: Trading symbol
            timeframe: Timeframe (e.g., '1d', '1h', 'D')
            start_date: Start date
            end_date: End date
            
        Returns:
            Downloaded data or None if failed
        """
        if provider not in self.providers:
            logger.error(f"Provider {provider} not configured")
            return None
        
        try:
            provider_instance = self.providers[provider]
            
            if provider == 'bybit':
                # Map timeframe to Bybit format (valid intervals: 1, 5, 15, 60, 240, D, W, M)
                timeframe_map = {
                    'D': 'D',     # Daily 
                    '1d': 'D',    # Daily
                    '4h': '240',  # 4 hours = 240 minutes
                    '1h': '60',   # 1 hour = 60 minutes
                    '15m': '15',  # 15 minutes
                    '5m': '5',    # 5 minutes
                    '1m': '1'     # 1 minute
                }
                bybit_timeframe = timeframe_map.get(timeframe, timeframe)
                logger.info(f"Using Bybit timeframe: {bybit_timeframe} (from {timeframe})")
                
                data = provider_instance.download_complete_history(symbol, bybit_timeframe, start_date, end_date)
            else:
                logger.error(f"Unknown provider: {provider}")
                return None
            
            if data is not None and not data.empty:
                logger.info(f"Downloaded {len(data)} records from {provider}")
                return data
            else:
                logger.warning(f"No data received from {provider}")
                return None
                
        except Exception as e:
            logger.error(f"Error downloading data from {provider}: {e}")
            return None
    
    def validate_data(self, data: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """
        Validate and clean data.
        
        Args:
            data: Raw data DataFrame
            symbol: Trading symbol
            
        Returns:
            Validation result with cleaned data and report
        """
        try:
            # Validate and clean data
            cleaned_data, report = self.validator.validate_and_clean(data)
            
            logger.info(f"Data validation completed for {symbol}")
            logger.info(f"Valid records: {report['valid_records']}/{report['total_records']}")
            
            return {
                'data': cleaned_data,
                'report': report,
                'is_valid': report['is_valid']
            }
            
        except Exception as e:
            logger.error(f"Error validating data: {str(e)}")
            return {
                'data': None,
                'report': {'is_valid': False, 'errors': [str(e)]},
                'is_valid': False
            }
    
    def split_data(self, data: pd.DataFrame, split_config: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
        """
        Split data according to configuration.
        
        Args:
            data: Cleaned data DataFrame
            split_config: Split configuration
            
        Returns:
            Dictionary with split datasets
        """
        try:
            splits = {}
            
            if split_config.get('train_test_split'):
                config = split_config['train_test_split']
                train_data, test_data = self.splitter.train_test_split(
                    data, 
                    test_size=config.get('test_size', 0.2),
                    method=config.get('method', 'chronological')
                )
                splits['train'] = train_data
                splits['test'] = test_data
            
            if split_config.get('date_split'):
                config = split_config['date_split']
                date_splits = self.splitter.split_by_date(
                    data,
                    split_date=config['split_date']
                )
                splits.update(date_splits)
            
            if split_config.get('sliding_windows'):
                config = split_config['sliding_windows']
                windows = self.splitter.create_sliding_windows(
                    data,
                    window_size=config['window_size'],
                    step_size=config.get('step_size', 1)
                )
                splits['windows'] = windows
            
            logger.info(f"Data split into {len(splits)} datasets")
            return splits
            
        except Exception as e:
            logger.error(f"Error splitting data: {e}")
            return {}
    
    def store_data(self, data: pd.DataFrame, metadata: Dict[str, Any]) -> Optional[int]:
        """
        Store data and metadata in databases.
        
        Args:
            data: Data to store
            metadata: Dataset metadata
            
        Returns:
            Dataset ID or None if failed
        """
        try:
            # Store time series data
            self.timeseries_db.insert_data(data)
            logger.info(f"Stored {len(data)} records in time series database")
            
            # Store metadata
            dataset_id = self.metadata_db.insert_dataset_metadata(metadata)
            logger.info(f"Stored metadata with dataset ID: {dataset_id}")
            
            return dataset_id
            
        except Exception as e:
            logger.error(f"Error storing data: {e}")
            return None
    
    def store_validation_report(self, dataset_id: int, report: Dict[str, Any]) -> None:
        """
        Store validation report in metadata database.
        
        Args:
            dataset_id: Dataset ID
            report: Validation report
        """
        try:
            self.metadata_db.insert_validation_report(dataset_id, report)
            logger.info(f"Stored validation report for dataset {dataset_id}")
        except Exception as e:
            logger.error(f"Error storing validation report: {e}")
    
    def save_to_file(self, data: pd.DataFrame, filename: str, format: str = 'parquet') -> str:
        """
        Save data to file.
        
        Args:
            data: Data to save
            filename: Filename
            format: File format ('parquet', 'csv', 'json')
            
        Returns:
            File path
        """
        filepath = self.data_dir / filename
        
        try:
            if format == 'parquet':
                data.to_parquet(filepath, index=False)
            elif format == 'csv':
                data.to_csv(filepath, index=False)
            elif format == 'json':
                data.to_json(filepath, orient='records', date_format='iso')
            else:
                raise ValueError(f"Unsupported format: {format}")
            
            logger.info(f"Data saved to {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Error saving data to {filepath}: {e}")
            raise
    
    def run_pipeline(self, pipeline_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run the complete data pipeline.
        
        Args:
            pipeline_config: Pipeline configuration containing:
                - provider: Data provider
                - symbol: Trading symbol
                - timeframe: Timeframe
                - start_date: Start date
                - end_date: End date
                - splits: Split configurations
                - save_files: Whether to save files
                - store_db: Whether to store in database
                
        Returns:
            Pipeline execution results
        """
        results = {
            'success': False,
            'datasets': {},
            'metadata': {},
            'errors': []
        }
        
        try:
            # Initialize databases if storing
            if pipeline_config.get('store_db', False):
                self._init_databases()
            
            # Extract configuration
            provider = pipeline_config['provider']
            symbol = pipeline_config['symbol']
            timeframe = pipeline_config['timeframe']
            start_date = pipeline_config['start_date']
            end_date = pipeline_config['end_date']
            
            # Step 1: Download data
            logger.info(f"Starting pipeline for {provider} {symbol} {timeframe}")
            raw_data = self.download_data(provider, symbol, timeframe, start_date, end_date)
            if raw_data is not None:
                logger.info(f"Downloaded data type: {type(raw_data)}")
                if hasattr(raw_data, 'shape'):
                    logger.info(f"Downloaded data shape: {raw_data.shape}")
                if hasattr(raw_data, 'columns'):
                    logger.info(f"Downloaded data columns: {list(raw_data.columns)}")
                logger.info(f"Downloaded data head:\n{raw_data.head()}\n")
            else:
                logger.warning("Downloaded data is None.")

            if raw_data is None or (hasattr(raw_data, 'empty') and raw_data.empty):
                results['errors'].append("Failed to download data or data is empty")
                return results
            
            # Step 2: Validate data
            validation_result = self.validate_data(raw_data, symbol)

            if not validation_result['is_valid']:
                results['errors'].append("Data validation failed")
                # Si hay errores detallados, los agrego al log
                if 'errors' in validation_result['report']:
                    logger.error(f"Validation errors: {validation_result['report']['errors']}")
                # Continue with cleaned data even if validation failed

            cleaned_data = validation_result['data']
            validation_report = validation_result['report']
            
            # Step 3: Split data (if configured)
            datasets = {'full': cleaned_data}
            
            if pipeline_config.get('splits'):
                split_datasets = self.split_data(cleaned_data, pipeline_config['splits'])
                datasets.update(split_datasets)
            
            # Step 4: Store data (if configured)
            dataset_ids = {}
            
            if pipeline_config.get('store_db', False):
                for dataset_name, dataset_data in datasets.items():
                    metadata = {
                        'dataset_name': f"{symbol}_{timeframe}_{dataset_name}",
                        'provider': provider,
                        'symbol': symbol,
                        'timeframe': timeframe,
                        'start_date': start_date,
                        'end_date': end_date,
                        'total_records': len(dataset_data),
                        'additional_metadata': {
                            'split_type': dataset_name,
                            'pipeline_config': pipeline_config
                        }
                    }
                    
                    dataset_id = self.store_data(dataset_data, metadata)
                    if dataset_id:
                        dataset_ids[dataset_name] = dataset_id
                        
                        # Store validation report for full dataset
                        if dataset_name == 'full':
                            self.store_validation_report(dataset_id, validation_report)
            
            # Step 5: Save files (if configured)
            file_paths = {}
            
            if pipeline_config.get('save_files', False):
                for dataset_name, dataset_data in datasets.items():
                    filename = f"{symbol}_{timeframe}_{dataset_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"
                    file_path = self.save_to_file(dataset_data, filename)
                    file_paths[dataset_name] = file_path
            
            # Store metadata using enhanced metadata manager
            metadata_info = {
                'dataset_name': f"{symbol}_{timeframe}",
                'provider': provider,
                'symbol': symbol,
                'timeframe': timeframe,
                'start_date': start_date,  # Already a string
                'end_date': end_date,      # Already a string
                'total_records': len(cleaned_data),
                'validation_report': validation_report,
                'splits': list(datasets.keys()),
                'file_paths': file_paths,
                'dataset_ids': dataset_ids
            }
            
            self.metadata_manager.store_metadata(metadata_info)
            
            results.update({
                'success': True,
                'datasets': {name: len(data) for name, data in datasets.items()},
                'metadata': metadata_info,
                'validation_report': validation_report,
                'file_paths': file_paths,
                'dataset_ids': dataset_ids
            })
            
            # Store to PostgreSQL if enabled
            if pipeline_config.get('store_postgresql', False):
                logger.info("Storing processed data to PostgreSQL...")
                postgresql_success = False
                
                try:
                    # Find the full dataset file (contains all processed data)
                    full_dataset_path = None
                    for name, path in file_paths.items():
                        if 'full' in name.lower():
                            full_dataset_path = path
                            break
                    
                    if full_dataset_path:
                        postgresql_success = store_processed_data_to_postgresql(
                            full_dataset_path,
                            DEFAULT_CONNECTION_PARAMS,
                            table_name="market_data_clean"
                        )
                        
                        if postgresql_success:
                            logger.info("✅ Data successfully stored to PostgreSQL")
                            results['postgresql_storage'] = {'success': True, 'table': 'market_data_clean'}
                        else:
                            logger.warning("❌ Failed to store data to PostgreSQL")
                            results['postgresql_storage'] = {'success': False, 'error': 'Storage failed'}
                    else:
                        logger.warning("No full dataset file found for PostgreSQL storage")
                        results['postgresql_storage'] = {'success': False, 'error': 'No full dataset found'}
                        
                except Exception as e:
                    logger.error(f"PostgreSQL storage error: {e}")
                    results['postgresql_storage'] = {'success': False, 'error': str(e)}
            
            logger.info("Pipeline completed successfully")
            
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            results['errors'].append(str(e))
            
        finally:
            # Cleanup
            if pipeline_config.get('store_db', False):
                self._cleanup_databases()
        
        return results
    
    def get_pipeline_status(self) -> Dict[str, Any]:
        """
        Get pipeline status and statistics.
        
        Returns:
            Pipeline status information
        """
        return {
            'providers': list(self.providers.keys()),
            'data_directory': str(self.data_dir),
            'metadata_files': len(list(self.data_dir.glob('*.json'))),
            'data_files': len(list(self.data_dir.glob('*.parquet'))),
            'config': self.config
        }


# Example configuration
EXAMPLE_CONFIG = {
    'data_dir': 'data/processed',
    'db_config': {
        'host': 'localhost',
        'port': 5432,
        'database': 'exodus_data',
        'user': 'postgres',
        'password': 'your_password'
    },
    'providers': {
        'bybit': {
            'api_key': 'your_api_key',
            'api_secret': 'your_api_secret',
            'testnet': True
        }
    },
    'validation_config': {
        'handle_missing': 'interpolate',
        'outlier_method': 'iqr',
        'outlier_threshold': 1.5
    },
    'split_config': {
        'train_test_split': {
            'test_size': 0.2,
            'method': 'chronological'
        }
    }
}

# Example pipeline configuration
EXAMPLE_PIPELINE_CONFIG = {
    'provider': 'bybit',
    'symbol': 'BTCUSDT',
    'timeframe': '1h',
    'start_date': datetime.now() - timedelta(days=30),
    'end_date': datetime.now(),
    'splits': {
        'train_test_split': {
            'test_size': 0.2,
            'method': 'chronological'
        }
    },
    'save_files': True,
    'store_db': True
}


def main():
    """Example usage of the crypto pipeline."""
    # Initialize pipeline
    pipeline = CryptoPipeline(EXAMPLE_CONFIG)
    
    # Run pipeline
    results = pipeline.run_pipeline(EXAMPLE_PIPELINE_CONFIG)
    
    # Print results
    print("Pipeline Results:")
    print(f"Success: {results['success']}")
    print(f"Datasets: {results['datasets']}")
    print(f"Validation Report: {results['validation_report']}")
    
    if results['errors']:
        print(f"Errors: {results['errors']}")


if __name__ == "__main__":
    main()
