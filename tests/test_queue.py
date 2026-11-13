from queuepilot.queue import Queue
import pytest

def test_idempotency_and_ack():
    now=[100.0];q=Queue(clock=lambda:now[0])
    jid=q.enqueue('email',{'x':1},idem_key='k')
    assert q.enqueue('email',{'x':1},idem_key='k')==jid
    with pytest.raises(ValueError):q.enqueue('email',{'x':2},idem_key='k')
    job=q.claim('worker-A');assert job.id==jid and job.attempts==1
    assert q.claim('worker-B') is None
    with pytest.raises(ValueError):q.complete(jid,'worker-B')
    q.complete(jid,'worker-A')
    assert q.status(jid)['status']=='done'

def test_backoff_and_dead_letter():
    now=[0.0];q=Queue(clock=lambda:now[0]);jid=q.enqueue('f',{},max_attempts=2)
    job=q.claim('w');q.fail(job.id,'w','oops')
    assert q.claim('w') is None
    now[0]=2
    job=q.claim('w');assert job.attempts==2
    q.fail(jid,'w','still failing')
    assert q.status(jid)['status']=='dead'

def test_reclaim_after_lease_expiration():
    now=[0.0];q=Queue(clock=lambda:now[0]);jid=q.enqueue('foo',{},max_attempts=2)
    assert q.claim('worker1',lease_seconds=3)
    now[0]=4
    assert q.claim('worker2').attempts==2
    with pytest.raises(ValueError):q.complete(jid,'worker1')
    q.complete(jid,'worker2')

def test_validation():
    q=Queue()
    with pytest.raises(ValueError):q.enqueue('',{})
    with pytest.raises(ValueError):q.claim('',lease_seconds=0)
