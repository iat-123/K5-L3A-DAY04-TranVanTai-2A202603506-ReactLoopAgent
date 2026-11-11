"""Tests cho cải tiến CP5: nhắc model đọc incident được dẫn tới (lỗi H1/H6 ở eval lần 1)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent import run_agent
from status_tools import StatusTools
from test_lab import FakeProvider, tool_call, final

# h02n9572mx9y có update "Please refer to ... /incidents/xr3myzj7ms51".
READ_H02 = '{"provider":"github","incident_id":"h02n9572mx9y"}'
READ_XR3 = '{"provider":"github","incident_id":"xr3myzj7ms51"}'


def details_url(incident_id):
    return StatusTools().get_incident_details('github', incident_id)['url']


class FollowLinkTests(unittest.TestCase):
    def test_unread_linked_incident_triggers_one_reminder(self):
        fake = FakeProvider([tool_call('1', 'get_incident_details', READ_H02),
                             final('Xong ' + details_url('h02n9572mx9y')),
                             tool_call('2', 'get_incident_details', READ_XR3),
                             final('Xong ' + details_url('h02n9572mx9y'))])
        result = run_agent('Theo liên kết', fake, StatusTools(), max_steps=6)
        self.assertEqual(result['status'], 'completed')
        events = [x['event'] for x in result['trace']]
        self.assertEqual(events.count('validation_unfollowed_link'), 1)
        self.assertIn('xr3myzj7ms51', fake.histories[2][-1]['content'])
        self.assertEqual([x['arguments'] for x in result['trace'] if x['event'] == 'tool'], [READ_H02, READ_XR3])

    def test_reminder_only_once_when_model_declines(self):
        fake = FakeProvider([tool_call('1', 'get_incident_details', READ_H02),
                             final('Không đọc tiếp ' + details_url('h02n9572mx9y')),
                             final('Chưa đọc incident liên quan ' + details_url('h02n9572mx9y'))])
        result = run_agent('x', fake, StatusTools(), max_steps=6)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual([x['event'] for x in result['trace']].count('validation_unfollowed_link'), 1)

    def test_no_reminder_without_budget(self):
        fake = FakeProvider([tool_call('1', 'get_incident_details', READ_H02),
                             final('Xong ' + details_url('h02n9572mx9y'))])
        result = run_agent('x', fake, StatusTools(), max_steps=3)
        self.assertEqual(result['status'], 'completed')
        self.assertNotIn('validation_unfollowed_link', [x['event'] for x in result['trace']])


if __name__ == '__main__':
    unittest.main()
