from queuepilot.queue import Queue
from queuepilot.worker import Worker

def test_worker_runs_handler_once():
    q=Queue();out=[];job=q.enqueue('add',{'value':5})
    w=Worker(q,'local',{'add':lambda data:out.append(data['value'])})
    assert w.run_once() and out==[5]
    assert q.status(job)['status']=='done'
    assert not w.run_once()

def test_handler_failure_requeues():
    q=Queue();job=q.enqueue('missing',{})
    assert Worker(q,'local',{}).run_once()
    assert q.status(job)['status']=='pending'
    assert q.status(job)['last_error'].startswith('KeyError')
