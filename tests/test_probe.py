import unittest

from probe import HeartbeatMonitor, parse_probe_payload, websocket_url


class ProbeParsingTests(unittest.TestCase):
    def test_maps_stable_node_id_to_name_and_heartbeat_age(self):
        payload = {
            "servers": [
                {
                    "id": "3f6c305b-0d4e-4b33-8393-39a40bdb997d",
                    "name": "ACLClouds-1",
                    "report_interval": 60,
                }
            ],
            "latestReportUpdates": [
                {
                    "serverId": "3f6c305b-0d4e-4b33-8393-39a40bdb997d",
                    "reportTs": 1_000_000,
                    "reportAgeMs": 12_500,
                }
            ],
        }
        nodes = parse_probe_payload(payload, now_ms=2_000_000)
        node = nodes["3f6c305b-0d4e-4b33-8393-39a40bdb997d"]
        self.assertEqual(node.name, "ACLClouds-1")
        self.assertEqual(node.report_interval_seconds, 60)
        self.assertEqual(node.report_age_seconds, 12.5)

    def test_websocket_url_and_batch_heartbeat(self):
        node_id = "3f6c305b-0d4e-4b33-8393-39a40bdb997d"
        self.assertEqual(
            websocket_url("https://tz.ssxi.de/api/servers", [node_id]),
            f"wss://tz.ssxi.de/api/ws?subscribe={node_id}",
        )
        monitor = HeartbeatMonitor("https://tz.ssxi.de/api/servers")
        monitor.update_ids([node_id])
        monitor.ingest_message(
            '{"type":"batchUpdate","updates":[{"serverId":"'
            + node_id
            + '","samples":[{"ts":1,"data":{"cpu":1}}]}]}'
        )
        snapshot = monitor.snapshot()
        self.assertIn(node_id, snapshot["heartbeats"])
        self.assertIsNotNone(snapshot["last_message_at"])
    def test_computes_age_when_api_omits_report_age(self):
        payload = {
            "servers": [{"id": "node-123456789012", "name": "Bot", "report_interval": 30}],
            "latestReportUpdates": [
                {"serverId": "node-123456789012", "reportTs": 1_000_000}
            ],
        }
        node = parse_probe_payload(payload, now_ms=1_090_000)["node-123456789012"]
        self.assertEqual(node.report_age_seconds, 90)


if __name__ == "__main__":
    unittest.main()
