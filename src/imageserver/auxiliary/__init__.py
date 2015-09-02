"""
Additional background processes that are spawned by the image server to provide
a long-running service. Currently these services exist:

* log_server - The centralised message logging service
* stats_server - The centralised statistics logging service
* task_server - Service for running background tasks from the internal task queue
"""
