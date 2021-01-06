import multiprocessing
import signal
from signal import SIGINT, SIG_IGN
from queue import Empty as EmptyQueue
import sys
import tqdm
from functools import partial

import logging
from .logger import setup_logger_child_process
logger = logging.getLogger(__name__)

class MultiProcessTqdm(object):
    def __init__(self, message_queue, tqdm_id, *args, **kwargs):
        self.message_queue = message_queue
        self.tqdm_id = tqdm_id
        message = (multiprocessing.current_process().name, "__init__", args, kwargs)
        self.message_queue.put((self.tqdm_id, message))

    def __enter__(self, *args, **kwargs):
        message = (multiprocessing.current_process().name, "__enter__", args, kwargs)
        self.message_queue.put((self.tqdm_id, message))
        return self

    def __exit__(self, *args, **kwargs):
        message = (multiprocessing.current_process().name, "__exit__", args, kwargs)
        self.message_queue.put((self.tqdm_id, message))

    def __getattr__(self, method_name):
        def _missing(*args, **kwargs):
            message = (multiprocessing.current_process().name, method_name, args, kwargs)
            self.message_queue.put((self.tqdm_id, message))
        return _missing

class GlobalMultiProcessTqdm(MultiProcessTqdm):
    # We don't want to init so no message is passed. Also the id is not applicable. 
    def __init__(self, message_queue):
        self.message_queue = message_queue
        self.tqdm_id = 0

def get_multi_tqdm(message_queue, tqdms_list, *args, **kwargs):
    tqdm_id = len(tqdms_list)
    # kwargs["mininterval"] = 1 # Slow it down
    multi_tqdm = MultiProcessTqdm(message_queue, tqdm_id, *args, **kwargs)
    tqdms_list.append(multi_tqdm)
    return multi_tqdm

terminate = False
def handler(signal_received, frame):
    global terminate
    terminate = True

# Signal handling for multiprocess. The "correct" answer doesn't work on windows at all.
# Using the version with a very slight race condition. Don't ctrl-c in that miniscule time window...
# https://stackoverflow.com/questions/11312525/catch-ctrlc-sigint-and-exit-multiprocesses-gracefully-in-python
def init_worker(logging_queue):
    setup_logger_child_process(logging_queue)    
    signal.signal(SIGINT, SIG_IGN)

def task_wrapper(tqdm_queue, global_tqdm_queue, operation, *args):
    tqdms_list = []
    tqdm_partial = partial(get_multi_tqdm, tqdm_queue, tqdms_list)
    global_tqdm = GlobalMultiProcessTqdm(global_tqdm_queue)
    return operation(*args, tqdm_partial, global_tqdm)

class TqdmMultiProcessPool(object):
    def __init__(self, process_count):
        self.mp_manager = multiprocessing.Manager()
        self.logging_queue = self.mp_manager.Queue()
        self.tqdm_queue = self.mp_manager.Queue()
        self.global_tqdm_queue = self.mp_manager.Queue()
        self.process_count = process_count
        worker_init_function = partial(init_worker, self.logging_queue)        
        self.mp_pool = multiprocessing.Pool(self.process_count, worker_init_function)

    def map(self, global_tqdm, tasks, on_error, on_done):

        self.previous_signal_int = signal.signal(SIGINT, handler)

        tqdms = {} # {} for _ in range(process_count)]

        async_results = []
        for operation, args in tasks:
            wrapper_args = tuple([self.tqdm_queue, self.global_tqdm_queue, operation] + list(args))
            async_results.append(self.mp_pool.apply_async(task_wrapper, wrapper_args))

        completion_status = [False for _ in async_results]
        countdown = len(completion_status)
        task_results = [None for _ in async_results]
        while countdown > 0 and not terminate:
            # Worker Logging
            try:
                logger_record = self.logging_queue.get_nowait()
                getattr(logger, logger_record.levelname.lower())(logger_record.getMessage())
            except (EmptyQueue, InterruptedError):
                pass

            # Worker tqdms
            try:
                count = 0
                while True:
                    tqdm_id, tqdm_message = self.tqdm_queue.get_nowait()
                    process_id, method_name, args, kwargs = tqdm_message
                    process_id = int(process_id[-1])
                    if process_id not in tqdms:
                        tqdms[process_id] = {}

                    if method_name == "__init__":
                        tqdms[process_id][tqdm_id] = tqdm.tqdm(*args, **kwargs)
                    else:
                        getattr(tqdms[process_id][tqdm_id], method_name)(*args, **kwargs)

                    count += 1
                    if count > 1000:
                        logger.info("Tqdm worker queue flood.")
            except (EmptyQueue, InterruptedError):
                pass

            # Global tqdm
            try:
                count = 0                    
                while True:
                    tqdm_id, tqdm_message = self.global_tqdm_queue.get_nowait()
                    process_id, method_name, args, kwargs = tqdm_message
                    getattr(global_tqdm, method_name)(*args, **kwargs)

                    count += 1
                    if count > 1000:
                        logger.info("Tqdm global queue flood.")
            except (EmptyQueue, InterruptedError):
                pass

            # Task Completion
            for i, async_result in enumerate(async_results):
                if completion_status[i]:
                    continue
                if async_result.ready():
                    task_result = async_result.get()
                    task_results[i] = task_result
                    completion_status[i] = True
                    countdown -= 1

                    # Task failed, do on_error
                    if not task_result:
                        on_error(task_result)

                    on_done(task_result)

        if terminate:
            logger.info('SIGINT or CTRL-C detected, closing pool. Please wait.')
            self.mp_pool.close()

        # Clear out remaining message queues. Sometimes get_nowait returns garbage
        # without erroring, just catching all exceptions as we don't care that much
        # about logging messages.
        try:
            while True:
                logger_record = self.logging_queue.get_nowait()
                getattr(logger, logger_record.levelname.lower())(logger_record.getMessage())
        except (EmptyQueue, InterruptedError):
            pass
        except Exception:
            pass

        try:
            while True:
                tqdm_id, tqdm_message = self.global_tqdm_queue.get_nowait()
                process_id, method_name, args, kwargs = tqdm_message
                getattr(global_tqdm, method_name)(*args, **kwargs)
        except (EmptyQueue, InterruptedError):
            pass

        try:
            while True:
                tqdm_record = self.tqdm_queue.get_nowait()
                tqdm_id, tqdm_message = tqdm_record
                process_id, method_name, args, kwargs = tqdm_message
                process_id = int(process_id[-1])
                if method_name == "__init__":
                    tqdms[process_id][tqdm_id] = tqdm.tqdm(*args, **kwargs)
                else:
                    getattr(tqdms[process_id][tqdm_id], method_name)(*args, **kwargs)
        except (EmptyQueue, InterruptedError):
            pass

        if terminate:
            logger.info('Terminating.')            
            for key, process_tqdms in tqdms.items():
                for key, tqdm_instance in process_tqdms.items():
                    if tqdm_instance:
                        tqdm_instance.close()
            sys.exit(0) # Will trigger __exit__

        signal.signal(SIGINT, self.previous_signal_int)

        return task_results