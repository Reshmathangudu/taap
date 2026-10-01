"""
Central retry utilities for Risk Tier Agent.
 
Uses exponential backoff with jitter.
Retries only transient failures.
 
Author: Risk Tier Team
"""
 
from functools import wraps
import logging
import random
import time
 
logger = logging.getLogger(__name__)
 
 
class RetryException(Exception):
    """Raised when retry attempts are exhausted."""
    pass
 
 
def retry(
    max_attempts: int = 3,
    initial_delay: float = 2,
    backoff: float = 2,
    max_delay: float = 30,
    retry_exceptions=(Exception,),
):
    """
    Generic retry decorator.
 
    Args:
        max_attempts: Maximum retry attempts
        initial_delay: Initial wait time
        backoff: Exponential multiplier
        max_delay: Maximum delay
        retry_exceptions: Exceptions eligible for retry
    """
 
    def decorator(func):
 
        @wraps(func)
        def wrapper(*args, **kwargs):
 
            delay = initial_delay
            last_exception = None
 
            for attempt in range(1, max_attempts + 1):
 
                try:
                    logger.info(
                        f"{func.__name__}: Attempt {attempt}/{max_attempts}"
                    )
                    return func(*args, **kwargs)
 
                except retry_exceptions as ex:
 
                    last_exception = ex
 
                    if attempt == max_attempts:
                        logger.error(
                            f"{func.__name__}: Failed after {max_attempts} attempts"
                        )
                        raise RetryException(str(ex)) from ex
 
                    sleep_time = min(delay, max_delay)
 
                    # Add small jitter
                    sleep_time += random.uniform(0, 1)
 
                    logger.warning(
                        f"{func.__name__}: Attempt {attempt} failed."
                        f" Retrying in {sleep_time:.2f}s"
                    )
 
                    time.sleep(sleep_time)
 
                    delay *= backoff
 
        return wrapper
 
    return decorator
 