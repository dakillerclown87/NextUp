"""Shuffle bags stored alongside the queue; restarting never resets a reply cycle."""
import hashlib
import json
import secrets


def choose_reply(queue, command):
    choices = list(dict.fromkeys(x.strip() for x in command['reply'].splitlines() if x.strip()))
    signature = hashlib.sha256(json.dumps(choices).encode()).hexdigest()
    pools = queue.state.setdefault('reply_pools', {})
    pool = pools.get(command['name'], {})
    if pool.get('signature') != signature:
        pool = {'signature': signature, 'remaining': [], 'last': None}
        pools[command['name']] = pool
    if not pool['remaining']:
        order = list(range(len(choices)))
        secrets.SystemRandom().shuffle(order)
        if len(order) > 1 and order[-1] == pool['last']:
            order[0], order[-1] = order[-1], order[0]
        pool['remaining'] = order
    index = pool['remaining'].pop()
    pool['last'] = index
    queue.save()
    return choices[index]
