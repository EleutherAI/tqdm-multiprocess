from time import sleep
import multiprocessing

import logging
from tqdm_multiprocess.logger import setup_logger_tqdm
logger = logging.getLogger(__name__)

from tqdm_multiprocess import TqdmMultiProcessPool

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