# gunicorn_config.py
import threading
import time as time_module
from datetime import datetime

def post_worker_init(worker):
    """Start background threads AFTER each gunicorn worker starts"""
    # We need to import here because the module isn't fully loaded yet
    from bot import message_queue, _process_single_message, four_hour_auto_post, storage
    import logging
    
    logger = logging.getLogger(__name__)
    
    def process_messages_worker():
        logger.info(f"[WORKER-THREAD] Started in gunicorn worker")
        while True:
            try:
                sender_id, text, message_id = message_queue.get()
                logger.info(f"[WORKER-THREAD] Got message from queue. Queue size: {message_queue.qsize()}")
                _process_single_message(sender_id, text, message_id)
                message_queue.task_done()
            except Exception as e:
                logger.error(f"[WORKER-THREAD] Error: {e}")
                message_queue.task_done()
    
    # Start message processor threads
    for i in range(2):
        t = threading.Thread(target=process_messages_worker, daemon=True)
        t.start()
        logger.info(f"[WORKER-THREAD] Started thread {i+1} in gunicorn worker {worker.pid}")
    
    def scheduler_loop():
        logger.info("[SCHEDULER-THREAD] Started in gunicorn worker")
        while True:
            try:
                time_module.sleep(3600)  # Disabled in debug
            except Exception as e:
                logger.error(f"[SCHEDULER-THREAD] Error: {e}")
    
    threading.Thread(target=scheduler_loop, daemon=True).start()
