import unittest

from fastapi.testclient import TestClient

from crm_support_ui.app import create_app
from crm_support_ui.dataverse_gateway import DataverseGateway


FORMATTED = "@OData.Community.Display.V1.FormattedValue"


class FakeClient:
    environment = "https://developersolutions.crm5.dynamics.com"

    def __init__(self):
        self.query = None

    def get(self, path, params=None):
        if path == "WhoAmI":
            return {"UserId": "24ff8ec1-f6dc-ed11-a7c7-000d3a82cdb2"}
        if path.startswith("systemusers("):
            return {"fullname": "Test User", "domainname": "test@example.com"}
        if path == "gc_techsupportincidents":
            self.query = params
            return {
                "value": [
                    {
                        "activityid": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                        "subject": "现场交流",
                        "description": "介绍 SpreadJS",
                        "actualend": "2026-07-21T00:00:00Z",
                        "actualend" + FORMATTED: "2026/07/21 8:00",
                        "createdon" + FORMATTED: "2026/07/22 10:00",
                        "modifiedon" + FORMATTED: "2026/07/22 10:00",
                        "_createdby_value" + FORMATTED: "Test User",
                        "_gc_account_value" + FORMATTED: "葡萄城软件",
                        "_gc_accounttechsupport_value": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                        "_gc_accounttechsupport_value" + FORMATTED: "葡萄城软件 (技术支持)",
                        "_gc_opportunity_value" + FORMATTED: "",
                        "_gc_opportunitytechsupport_value": None,
                        "_regardingobjectid_value" + FORMATTED: "葡萄城软件 (技术支持)",
                    }
                ]
            }
        raise AssertionError(path)

    def get_entity(self, logical_name):
        self.assert_equal_entity = logical_name
        return {
            "PrimaryIdAttribute": "activityid",
            "EntitySetName": "gc_techsupportincidents",
        }


class HistoryTests(unittest.TestCase):
    def test_lists_cases_created_by_current_user_with_source_links(self):
        client = FakeClient()
        result = DataverseGateway(lambda: client).list_incidents()

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["user"]["name"], "Test User")
        item = result["items"][0]
        self.assertEqual(item["source_type"], "account")
        self.assertEqual(item["source_name"], "葡萄城软件 (技术支持)")
        self.assertEqual(item["actual_end"], "2026/07/21 8:00")
        self.assertIn("etn=gc_techsupportincident", item["url"])
        self.assertIn("etn=gc_accounttechsupport", item["source_url"])
        self.assertEqual(
            client.query["$filter"],
            "_createdby_value eq 24ff8ec1-f6dc-ed11-a7c7-000d3a82cdb2",
        )

    def test_history_endpoint_returns_gateway_results(self):
        class FakeGateway:
            def list_incidents(self, limit):
                return {"count": 0, "items": [], "user": {"name": "Test User"}}

        with TestClient(create_app(FakeGateway())) as http:
            response = http.get("/api/incidents", params={"limit": 25})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)


if __name__ == "__main__":
    unittest.main()
