"""Utility functions for logging."""
import logging
import os

def setup_logging(name, log_dir="/var/log/pod-migration"):
    """Set up logging configuration."""
    os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # File handler
    fh = logging.FileHandler(os.path.join(log_dir, f"{name}.log"))
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    return logger
