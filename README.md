# tqdm-multiprocess
Using queues, tqdm-multiprocess supports multiple worker processes, each with multiple tqdm progress bars, displaying them cleanly through the main process. It offers similar functionality for python logging. 

Currently doesn't support tqdm(iterator), you will need to intialize tqdm with a total and update manually.
