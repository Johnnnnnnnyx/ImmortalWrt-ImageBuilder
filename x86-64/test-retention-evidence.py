"""Retention diagnostics must identify fields without exposing their values."""
import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest


class EvidenceTest(unittest.TestCase):
    def test_evidence_has_file_and_field_hashes_without_secret_values(self):
        source = Path(__file__).with_name('test-sysupgrade.py')
        tree = ast.parse(source.read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == 'retention_snapshot')
        def run(client, command):
            if command.startswith('sha256sum '):
                return 'a' * 64 + '  /etc/config/meowx\n'
            if command.startswith('uci -q show'):
                return "meowx.config.api_secret='PRIVATE_VALUE'\nPRIVATE_CONTINUATION\n"
            if command == 'cat /etc/shadow':
                return 'root:PRIVATE_PASSWORD:0:0:99999:7:::\n'
            if command == 'uci changes':
                return "meowx.config.api_secret='PRIVATE_PENDING'\n"
            return '1'
        with tempfile.TemporaryDirectory() as directory:
            namespace = dict(hashlib=hashlib, json=json, image=Path(directory) / 'test.img', run=run)
            exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
            result = namespace['retention_snapshot'](None, ['/etc/config/meowx'], 'baseline')
            text = (Path(directory) / 'retention-baseline.json').read_text()
            self.assertNotIn('PRIVATE_', text)
            self.assertEqual(result['files']['/etc/config/meowx'], 'a' * 64)
            self.assertEqual(list(result['uci_fields']), ['meowx.config.api_secret'])
            self.assertEqual(list(result['shadow_accounts']), ['root'])


if __name__ == '__main__':
    unittest.main()
