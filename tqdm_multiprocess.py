import multiprocessing
import signal
from signal import SIGINT, SIG_IGN
from queue import Empty as EmptyQueue
import sys
from time import sleep
import tqdm
from functools import partial

import logging
from logger import setup_logger_tqdm, setup_logger_child_process
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

def get_multi_tqdm(message_queue, tqdms_list, *args, **kwargs):
    tqdm_id = len(tqdms_list)
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
def init_worker():
    signal.signal(SIGINT, SIG_IGN)

def task_wrapper(logging_queue, tqdm_queue, operation, *args):
    tqdms_list = []
    setup_logger_child_process(logging_queue)
    tqdm_partial = partial(get_multi_tqdm, tqdm_queue, tqdms_list)
    return operation(*args, tqdm_partial)

class TqdmMultiProcessPool(object):
    def __init__(self):
        pass

    def map(self, process_count, initial_tasks, on_error):
        previous_signal_int = signal.signal(SIGINT, handler)
        with multiprocessing.Pool(process_count, init_worker) as pool:
            tqdms = [{} for _ in range(process_count)]

            m = multiprocessing.Manager()
            logging_queue = m.Queue()
            tqdm_queue = m.Queue()

            async_results = []
            for operation, args in initial_tasks:
                wrapper_args = tuple([logging_queue, tqdm_queue, operation] + list(args))
                async_results.append(pool.apply_async(task_wrapper, wrapper_args))

            completion_status = [False for _ in async_results]
            countdown = len(completion_status)
            task_results = []
            while countdown > 0 and not terminate:
                try:
                    logger_record = logging_queue.get_nowait()
                    getattr(logger, logger_record.levelname.lower())(logger_record.getMessage())
                except (EmptyQueue, InterruptedError):
                    pass

                try:
                    tqdm_id, tqdm_message = tqdm_queue.get_nowait()
                    process_id, method_name, args, kwargs = tqdm_message
                    process_id = int(process_id[-1]) - 1
                    if method_name == "__init__":
                        tqdms[process_id][tqdm_id] = tqdm.tqdm(*args, **kwargs)
                    else:
                        getattr(tqdms[process_id][tqdm_id], method_name)(*args, **kwargs)
                except (EmptyQueue, InterruptedError):
                    pass

                for i, async_result in enumerate(async_results):
                    if completion_status[i]:
                        continue
                    if async_result.ready():
                        task_result = async_result.get()
                        task_results.append(task_result)
                        completion_status[i] = True
                        countdown -= 1

                        # Task failed, do on_error
                        if not task_result:
                            on_error()

            # Clear out remaining message queue
            try:
                while True:
                    logger_record = logging_queue.get_nowait()
                    getattr(logger, logger_record.levelname.lower())(logger_record.getMessage())
            except (EmptyQueue, InterruptedError):
                pass

            try:
                while True:
                    tqdm_id, tqdm_message = tqdm_queue.get_nowait()
                    process_id, method_name, args, kwargs = tqdm_message
                    process_id = int(process_id[-1]) - 1
                    if method_name == "__init__":
                        tqdms[process_id][tqdm_id] = tqdm.tqdm(*args, **kwargs)
                    else:
                        getattr(tqdms[process_id][tqdm_id], method_name)(*args, **kwargs)
            except (EmptyQueue, InterruptedError):
                pass

        if terminate:
            for tqdm_instance in tqdms:
                if tqdm_instance:
                    tqdm_instance.close()
            logger.info('\nSIGINT or CTRL-C detected, killing pool')
            sys.exit(0)

        signal.signal(SIGINT, previous_signal_int)

        return task_results

def some_other_function(tqdm_func):
    iterations1 = 100
    iterations2 = 5
    iterations3 = 2
    
    total_iterations = iterations1 * iterations2 * iterations3
    with tqdm_func(total=total_iterations, dynamic_ncols=True) as progress3:
        progress3.set_description("outer")
        for i in range(iterations3):
            logger.info("outer")
            total_iterations = iterations1 * iterations2
            with tqdm_func(total=total_iterations, dynamic_ncols=True) as progress2:
                progress2.set_description("middle")
                for j in range(iterations2):
                    logger.info("middle")
                    #for k in tqdm_func(range(iterations1), dynamic_ncols=True, desc="inner"):
                    with tqdm_func(total=iterations1, dynamic_ncols=True) as progress1:
                        for j in range(iterations1):
                            # logger.info("inner") # Spam slows down tqdm too much
                            progress1.set_description("innert")
                            sleep(0.01)
                            progress1.update()
                            progress2.update()
                            progress3.update()

    logger.warning(f"Warning test message. {multiprocessing.current_process().name}")
    logger.error(f"Error test message. {multiprocessing.current_process().name}")

        
# Multiprocessed
def example_multiprocessing_function(some_input, tqdm_func):  
    logger.debug(f"Debug test message - I won't show up in console. {multiprocessing.current_process().name}")
    logger.info(f"Info test message. {multiprocessing.current_process().name}")
    some_other_function(tqdm_func)
    return True

def error_callback():
    print("Error!")

def example():
    pool = TqdmMultiProcessPool()
    process_count = 4
    task_count = 10
    initial_tasks = [(example_multiprocessing_function, (i,)) for i in range(task_count)]    
    results = pool.map(process_count, initial_tasks, error_callback)
    print(results)

if __name__ == '__main__':
    logfile_path = "tqdm_multiprocessing_example.log"
    setup_logger_tqdm(logfile_path) # Logger will write messages using tqdm.write
    example() 

