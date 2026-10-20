import logging
import urllib.request
import urllib.parse
import json

logger = logging.getLogger(__name__)

class PrometheusClient:
    def __init__(self, base_url="http://localhost:9090", timeout=10.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def query(self, query_str):
        url = f"{self.base_url}/api/v1/query?query={urllib.parse.quote(query_str)}"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("status") == "success":
                    return data.get("data", {}).get("result", [])
                else:
                    logger.error(f"Prometheus query failed: {data.get('error')}")
                    return []
        except Exception as e:
            logger.error(f"Prometheus query error ({query_str}): {e}")
            return []

    def query_range(self, query_str, start_time, end_time, step="5s"):
        params = urllib.parse.urlencode({
            "query": query_str,
            "start": str(start_time),
            "end": str(end_time),
            "step": str(step)
        })
        url = f"{self.base_url}/api/v1/query_range?{params}"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("status") == "success":
                    return data.get("data", {}).get("result", [])
                else:
                    logger.error(f"Prometheus query_range failed: {data.get('error')}")
                    return []
        except Exception as e:
            logger.error(f"Prometheus query_range error ({query_str}): {e}")
            return []

    def get_label_values(self, label_name, match_metric=None):
        url = f"{self.base_url}/api/v1/label/{label_name}/values"
        if match_metric:
            url += f"?match[]={urllib.parse.quote(match_metric)}"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("status") == "success":
                    return data.get("data", [])
                return []
        except Exception as e:
            logger.error(f"Prometheus get_label_values error ({label_name}): {e}")
            return []
