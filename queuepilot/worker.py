"""Single-step worker with explicit retry semantics and no hidden side effects."""
from __future__ import annotations
from collections.abc import Callable
from .queue import Queue

class Worker:
    def __init__(self,queue:Queue,owner:str,handlers:dict[str,Callable[[dict],None]]):
        if not owner:raise ValueError('owner required')
        self.queue=queue;self.owner=owner;self.handlers=handlers
    def run_once(self)->bool:
        job=self.queue.claim(self.owner)
        if job is None:return False
        try:
            self.handlers[job.kind](job.payload)
        except Exception as error:
            self.queue.fail(job.id,self.owner,f'{type(error).__name__}: {error}')
        else:
            self.queue.complete(job.id,self.owner)
        return True
