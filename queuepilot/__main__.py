import argparse
from .queue import Queue

def main():
    p=argparse.ArgumentParser();p.add_argument('--db',default='queuepilot.sqlite')
    args=p.parse_args();q=Queue(args.db)
    jid=q.enqueue('send_receipt',{'recipient':'example.invalid','order':123},idem_key='demo-receipt-123')
    job=q.claim('local-demo')
    if job:
        print('Claimed',job)
        q.complete(job.id,'local-demo')
    print('Original job:',q.status(jid)); print('Queue totals:',q.counts())
if __name__=='__main__':main()
