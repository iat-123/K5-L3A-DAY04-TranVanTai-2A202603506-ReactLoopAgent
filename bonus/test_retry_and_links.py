"""Tests offline cho phần agent bonus: giới hạn retry 429 và link incident sang provider khác."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'bonus'))
from agent import run_agent, _linked_incidents
from bonus.tools import BonusTools
from test_agent import ScriptedProvider, call, final


class RetryLimitTests(unittest.TestCase):
    def test_persistent_429_stops_after_three_api_calls(self):
        tools = BonusTools(scenario='rate_limit_always')
        provider = ScriptedProvider([call(str(i), 'get_vercel_status', {}) for i in range(5)] + [final('Không xác định được Vercel')])
        result = run_agent('Kiểm tra Vercel', provider, tools, max_steps=8)
        self.assertEqual(result['status'], 'completed')
        executed = [x for x in result['trace'] if x['event'] == 'tool' and x['name'] == 'get_vercel_status']
        skipped = [x for x in result['trace'] if x['event'] == 'tool_skipped']
        self.assertEqual(len(executed), 3)                       # API chỉ bị gọi 3 lần
        self.assertEqual(tools.calls[('get_vercel_status', 'vercel')], 3)
        self.assertEqual(len(skipped), 2)                        # 2 lần sau bị chặn trong agent
        self.assertEqual(skipped[0]['result']['error'], 'RETRY_LIMIT_REACHED')
        self.assertIn('đã dừng retry', executed[-1]['result']['agent_note'])

    def test_single_429_then_success(self):
        tools = BonusTools(scenario='rate_limit_once')
        provider = ScriptedProvider([call('a', 'get_vercel_status', {}), call('b', 'get_vercel_status', {}), final()])
        result = run_agent('Kiểm tra Vercel', provider, tools, max_steps=5)
        self.assertEqual(result['status'], 'completed')
        first = json.loads(provider.histories[1][-1]['content'])
        self.assertEqual(first['error'], 'RATE_LIMITED')
        self.assertIn('1/3', first['agent_note'])
        self.assertEqual(json.loads(provider.histories[2][-1]['content'])['provider'], 'vercel')

    def test_model_skipping_retry_gets_one_reminder(self):
        tools = BonusTools(scenario='rate_limit_once')
        provider = ScriptedProvider([call('a', 'get_vercel_status', {}), final('Vercel không rõ'),
                                     call('b', 'get_vercel_status', {}), final('Vercel ổn')])
        result = run_agent('Kiểm tra Vercel', provider, tools, max_steps=6)
        self.assertEqual(result['status'], 'completed')
        events = [x['event'] for x in result['trace']]
        self.assertEqual(events.count('validation_unretried_rate_limit'), 1)
        self.assertEqual(sum(1 for x in result['trace'] if x.get('name') == 'get_vercel_status'), 2)
        self.assertEqual(result['answer'], 'Vercel ổn')

    def test_no_retry_reminder_after_limit_reached(self):
        tools = BonusTools(scenario='rate_limit_always')
        provider = ScriptedProvider([call(str(i), 'get_vercel_status', {}) for i in range(3)] + [final('Không xác định được Vercel')])
        result = run_agent('Kiểm tra Vercel', provider, tools, max_steps=8)
        self.assertEqual(result['status'], 'completed')
        self.assertNotIn('validation_unretried_rate_limit', [x['event'] for x in result['trace']])

    def test_main_lab_tools_still_use_default_prompt(self):
        from status_tools import StatusTools
        provider = ScriptedProvider([final()])
        run_agent('x', provider, StatusTools())
        self.assertIn('GitHub và Cloudflare', provider.histories[0][0]['content'])
        self.assertEqual({s['function']['name'] for s in provider.schemas[0]}, {'get_status', 'get_incident_details'})


class LinkedIncidentTests(unittest.TestCase):
    def test_provider_comes_from_link_domain(self):
        body = 'Due to an upstream incident at GitHub (https://www.githubstatus.com/incidents/93njd414rpbx), builds fail'
        self.assertEqual(_linked_incidents(body), [('github', '93njd414rpbx')])

    def test_unknown_domain_and_shortlinks_are_ignored(self):
        self.assertEqual(_linked_incidents('see https://example.com/incidents/abcdef12 and https://stspg.io/xyz'), [])


if __name__ == '__main__':
    unittest.main()
