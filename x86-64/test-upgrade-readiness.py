"""A successful SSH login alone must not permit rebooting an unready overlay."""
import ast
from pathlib import Path
import types
import unittest
from unittest.mock import Mock

source = Path(__file__).with_name('test-sysupgrade.py')
tree = ast.parse(source.read_text(encoding='utf-8'))
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'wait_ssh')


class ReadinessTest(unittest.TestCase):
    def run_wait(self, states, previous_boot=None):
        clock = Mock()
        elapsed = [0]
        clock.monotonic.side_effect = lambda: elapsed[0]
        clock.sleep.side_effect = lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds)
        clients = [Mock(state=state) for state in states]
        connected, commands = [], []

        def connect():
            client = clients[len(connected)] if len(connected) < len(clients) else clients[-1]
            connected.append(client)
            return client

        def run(client, command):
            commands.append(command)
            return {'cat /proc/sys/kernel/random/boot_id': 'new-boot',
                    'readlink /overlay/.fs_state': client.state, 'sync': ''}[command]

        namespace = dict(time=clock, paramiko=types.SimpleNamespace(SSHException=ConnectionError),
                         qemu=Mock(poll=lambda: None), connect=connect, run=run)
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
        result = namespace['wait_ssh'](previous_boot)
        return result, connected, commands

    def test_pending_first_boot_is_not_accepted_before_ready(self):
        result, connected, commands = self.run_wait(['1', '2'])
        self.assertEqual(len(connected), 2)
        connected[0].close.assert_called_once()
        self.assertIs(result, connected[1])
        self.assertEqual(commands[-1], 'sync')

    def test_new_boot_id_still_requires_ready_overlay(self):
        _, connected, _ = self.run_wait(['1', '2'], 'old-boot')
        self.assertEqual(len(connected), 2)

    def test_overlay_that_never_finishes_is_a_failure(self):
        with self.assertRaises(RuntimeError):
            self.run_wait(['1'])


if __name__ == '__main__':
    unittest.main()
