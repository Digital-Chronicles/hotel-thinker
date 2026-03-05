import requests

url = "https://api.sandbox.zengapay.com/v1/transfers"

payload = "{\"msisdn\":\"256773318456\",\"amount\":1000,\"external_reference\":\"400000\",\"narration\":\"Payout - 11200390191\"\n}"
headers = {
  'Authorization': 'Bearer <ZPYPUBK-f20d004a5f57fb563d482aa67488502b063d8e2823a3d1808af2852e83cbff85>',
  'Content-Type': 'application/json'
}

response = requests.request("POST", url, headers=headers, data = payload)

print(response.text.encode('utf8'))
