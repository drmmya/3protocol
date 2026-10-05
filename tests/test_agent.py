import tempfile,unittest
from pathlib import Path
from panel.agent import Agent
from panel.state import State
from panel.metrics import Metrics
class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.agent=Agent({'state':str(Path(self.tmp.name)/'db'),'endpoint':'203.0.113.2'},system=False)
    def tearDown(self): self.tmp.cleanup()
    def test_unknown_command(self):
        with self.assertRaises(ValueError): self.agent.dispatch({'action':'exec','command':'id'})
    def test_settings_input(self):
        with self.assertRaises(ValueError): self.agent.dispatch({'action':'settings','timezone':'../../tmp'})
    def test_job_failure_is_not_success(self):
        j=self.agent.job('test',lambda: (_ for _ in ()).throw(ValueError('expected failure')))
        self.agent.jobs[j]['thread'].join(2)
        self.assertEqual(self.agent.public_jobs()[0]['status'],'failed')
        self.assertIn('expected failure',self.agent.public_jobs()[0]['error'])
    def test_metrics_real_values(self):
        m=Metrics('lo').read();self.assertGreater(m['ram_total'],0);self.assertGreater(m['disk_total'],0)
        self.assertGreaterEqual(m['cpu'],0);self.assertLessEqual(m['cpu'],100)
