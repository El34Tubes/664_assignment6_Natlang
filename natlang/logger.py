import logging, sys
import os
def get_logger(name: str = "natlang"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        fmt = logging.Formatter('%(asctime)s %(levelname)s %(name)s — %(message)s')
        handler.setFormatter(fmt)
        logger.addHandler(handler)
        # add a rotating file handler for persistent logs
        try:
            log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
            os.makedirs(log_dir, exist_ok=True)
            file_path = os.path.join(log_dir, 'natlang.log')
            fh = logging.FileHandler(file_path, encoding='utf-8')
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except Exception:
            # if file handler cannot be added, continue with stdout only
            pass
        logger.setLevel(logging.INFO)
    return logger
