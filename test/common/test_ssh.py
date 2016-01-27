import unittest

from fabric.api import env, hosts, roles, run, task, runs_once, execute, local
import collections

class TestSsh(unittest.TestCase):

    def test_named_params(self):

        result = {"port": "80"}

        if result.get('host'):
            print_a_n_b(a=result.port, b=result.host)




@task
def fab_connect():
    run('ls -l')

if __name__ == '__main__':
    unittest.main()

def print_a_n_b(a="a", b="b"):
    print a
    print b