# tqdm-multiprocess
Using queues, tqdm-multiprocess supports multiple worker processes, each with multiple tqdm progress bars, displaying them cleanly through the main process.  

It also redirects logging from the subprocesses to the root logger in the main process.

Currently doesn't support tqdm(iterator), you will need to intialize tqdm with a total and update manually.

Due to the performance limits of the default Python multiprocess queue you need to update your global and worker process tqdms infrequently to avoid flooding the main process. I will attempt to implement a lock free ringbuffer at some point to address this.

## Installation

```bash
pip install tqdm-multiprocess
```

## Usage

*TqdmMultiProcessPool* creates a standard python multiprocessing pool with the desired number of processes. Under the hood it uses async_apply with an event loop to monitor a tqdm and logging queue, allowing the worker processes to redirect both their tqdm objects and logging messages to your main process.

As shown below, you create a list of tasks containing their function and a tuple with your parameters. The functions you pass in will need an extra "tqdm_func" argument on the end which you must use to initialize your tqdms. As mentioned above, passing iterators into the tqdm function is currently not supported, so set total=total_steps when setting up your tqdm, and then update the progress manually with the update() method. All other arguments to tqdm should work fine.

Once you have your task list, call the map() method on your pool, passing in the process count, task list and error callback function. The error callback will be trigerred if your task functions return anything evaluating as False (if not task_result in the source code).

### examples/basic_example.py

```python
from time import sleep
import multiprocessing
import tqdm

import logging
from tqdm_multiprocess.logger import setup_logger_tqdm
logger = logging.getLogger(__name__)

from tqdm_multiprocess import TqdmMultiProcessPool

iterations1 = 100
iterations2 = 5
iterations3 = 2
def some_other_function(tqdm_func, global_tqdm):
    
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
                            global_tqdm.update()

    logger.warning(f"Warning test message. {multiprocessing.current_process().name}")
    logger.error(f"Error test message. {multiprocessing.current_process().name}")

        
# Multiprocessed
def example_multiprocessing_function(some_input, tqdm_func, global_tqdm):  
    logger.debug(f"Debug test message - I won't show up in console. {multiprocessing.current_process().name}")
    logger.info(f"Info test message. {multiprocessing.current_process().name}")
    some_other_function(tqdm_func, global_tqdm)
    return True

def error_callback(result):
    print("Error!")

def done_callback(result):
    print("Done. Result: ", result)

def example():
    pool = TqdmMultiProcessPool()
    process_count = 4
    task_count = 10
    initial_tasks = [(example_multiprocessing_function, (i,)) for i in range(task_count)]    
    total_iterations = iterations1 * iterations2 * iterations3 * task_count
    with tqdm.tqdm(total=total_iterations, dynamic_ncols=True) as global_progress:
        global_progress.set_description("global")
        results = pool.map(process_count, global_progress, initial_tasks, error_callback, done_callback)
        print(results)

if __name__ == '__main__':
    logfile_path = "tqdm_multiprocessing_example.log"
    setup_logger_tqdm(logfile_path) # Logger will write messages using tqdm.write
    example()
```
