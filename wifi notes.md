https://domestic.mammotion.com/user-server/v1/user/oauth/token?
password={encrypted password}
grant_type=uR%2FNYIFr4h8EuvrHuhE0Nw%3D%3D&
client_secret=Ef5%2F5PrypABaNKUtlWkHQogMZTG5yrK1jXCqGmSo3NI%3D&
client_id=XG2kuRPLH%2Bw%2BKZ1f5Siq%2Bw%3D%3D&
username={encrypted username}

 hashMap.put("username", CryptUtil.getInstance().encryptionByAES(this.etEmail.getText().toString()));
            hashMap.put("client_id", CryptUtil.getInstance().encryptionByAES(HttpConstants.OAUTH_ALI_CLIENT_ID));
            hashMap.put("client_secret", CryptUtil.getInstance().encryptionByAES(HttpConstants.OAUTH_ALI_CLIENT_SECRET));
            hashMap.put("grant_type", CryptUtil.getInstance().encryptionByAES("password"));
            hashMap.put("password", CryptUtil.getInstance().encryptionByAES(this.etPassword.getText().toString()));

headers:
decrypt-type: 3
encrypt-key: RzyDSE8ZShW3Pl3BkFPii7y4749cxZRrlPjFAmtkXJuQSNv2O6lbyaJOj7KSo3pnzEfnU4WBQAadZvo6xFsXWmsiyzeiz2aFmNxtY/MgPTkW8zkerY0QNwOcHy0tWjjOFOIaAmKhfTL5EubKvKA/Rwpux0+o7sDuZAnWGhEijL9sOwlGLdZq3FLdWye8aYz37re1fYk3KMqWHadoryfq6wINyDbfety32ynRgHWetG1ScyBY9ns/ZXgTxJ2HcE0yuPeuHOAIW/0pWGMGb41EOxzvJrqvlUlpk/JwUSaL26CLlEg3dqUKn4RO2RlS2mPm08BTND7L+SNxzHCBaaUukw==
host: domestic.mammotion.com
app-version: google-Android 11,1.9.54
client-id:
4-ffff-ffffef05ac4a
client-type:
1

response
{
  "code": 0,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJncmFudF90eXBlIjoicGFzc3dvcmQiLCJ1c2VyX25hbWUiOiJtaWNoYWVsQGFydGh1ci5raXdpLm56IiwiYXV0aG9yaXphdGlvbl9jb2RlIjoiNVNjMThjV0ciLCJzY29wZSI6WyJyZWFkIl0sInVzZXJJbmZvcm1hdGlvbiI6eyJ1c2VySWQiOiI0MjA0MDA1MTg2NDk2MTAyNDAiLCJ1c2VyTmFtZSI6bnVsbCwiZnVsbE5hbWUiOm51bGwsIm5pY2tOYW1lIjpudWxsLCJnZW5kZXIiOiIwIiwibW9iaWxlIjpudWxsLCJlbWFpbCI6Im1pY2hhZWxAYXJ0aHVyLmtpd2kubnoiLCJhcmVhQ29kZSI6Ik5aTCIsImRvbWFpbkFiYnJldmlhdGlvbiI6Ik5aIiwicmVnaXN0ZXJUaW1lIjoiMjAyMi0xMS0wMyAxODowMTozNCIsImxhc3RMb2dpblRpbWUiOiIyMDIzLTA5LTA0IDIzOjA1OjM5In0sImV4cCI6MTY5NTE2NDczOSwianRpIjoiNWQ5ZGEyNDktMmJlNS00YjIxLTg0YjAtODVhNmEwOTVhMGExIiwiY2xpZW50X2lkIjoiTUFES0FMVUJBUyJ9.JgS77T6LPR6lLoMuhlpGhajdgZAHi8rpriWdUwCJTBc",
    "token_type": "bearer",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJncmFudF90eXBlIjoicGFzc3dvcmQiLCJ1c2VyX25hbWUiOiJtaWNoYWVsQGFydGh1ci5raXdpLm56IiwiYXV0aG9yaXphdGlvbl9jb2RlIjoiNVNjMThjV0ciLCJzY29wZSI6WyJyZWFkIl0sInVzZXJJbmZvcm1hdGlvbiI6eyJ1c2VySWQiOiI0MjA0MDA1MTg2NDk2MTAyNDAiLCJ1c2VyTmFtZSI6bnVsbCwiZnVsbE5hbWUiOm51bGwsIm5pY2tOYW1lIjpudWxsLCJnZW5kZXIiOiIwIiwibW9iaWxlIjpudWxsLCJlbWFpbCI6Im1pY2hhZWxAYXJ0aHVyLmtpd2kubnoiLCJhcmVhQ29kZSI6Ik5aTCIsImRvbWFpbkFiYnJldmlhdGlvbiI6Ik5aIiwicmVnaXN0ZXJUaW1lIjoiMjAyMi0xMS0wMyAxODowMTozNCIsImxhc3RMb2dpblRpbWUiOiIyMDIzLTA5LTA0IDIzOjA1OjM5In0sImF0aSI6IjVkOWRhMjQ5LTJiZTUtNGIyMS04NGIwLTg1YTZhMDk1YTBhMSIsImV4cCI6MTY5NjQ2MDczOSwianRpIjoiMTBmNjA5YTItOWVmOS00ZGY1LTljMTktZTkxNTk3MjAzMDFhIiwiY2xpZW50X2lkIjoiTUFES0FMVUJBUyJ9.jMEIyVKnGAqwN2qTI81v4i2ITk2sNrZIazTsmlOjfi4",
    "expires_in": 1295999,
    "scope": "read",
    "grant_type": "password",
    "authorization_code": "5Sc18cWG", // required for aliyun calls
    "userInformation": {
      "areaCode": "NZL",
      "domainAbbreviation": "NZ",
      "email": "{email from account}",
      "gender": "0",
      "userId": "420400518649610240"
    },
    "jti": "5d9da249-2be5-4b21-84b0-85a6a095a0a1"
  },
  "msg": "Request success"
}

// all POST calls
//

https://api.link.aliyun.com/living/account/region/get?x-ca-request-id=ba09de2f-aea6-4df9-a646-a759eb0e1e33
// get region for IOT calls

https://living-account.ap-southeast-1.aliyuncs.com/api/prd/loginbyoauth.json
body
loginByOauthRequest: {"country":"NZ",
"authCode":"5Sc18cWG",
"oauthPlateform":23,
"oauthAppKey":"34231230","riskControlInfo":{"altitude":"84.4000015258789","appVersion":"34","USE_OA_PWD_ENCRYPT":"true","utdid":"Y+vM4QToyx0DAGiNdXRlvrO0","netType":"wifi","latitude":"-38.0024067","umidToken":"KBoBwUFLPKdpmAKKM6b4Aeo5c\/9UDTGf","locale":"en_US","cellID":"6713","appVersionName":"1.9.54","deviceId":"bd30ae95-f971-4fed-a5be-49d74cf4a698","routerMac":"24:5a:4c:63:fe:a4","platformVersion":"30",
"appAuthToken":"KBoBwUFLPKdpmAKKM6b4Aeo5c\/9UDTGf",
"appID":"com.agilexrobotics","signType":"RSA","sdkVersion":"3.4.2","model":"Pixel 2 XL","USE_H5_NC":"true","platformName":"android","brand":"google","yunOSId":"","longitude":"175.3180863"}}



// create session with aliyun
https://ap-southeast-1.api-iot.aliyuncs.com/account/createSessionByAuthCode?x-ca-request-id=32dba207-99ac-4402-b9c7-98a28040fc80
{
  "code": 200,
  "data": {
    "identityId": "50e2op4d4a00f08b49cb52d098fb6e43a5f56396",
    "refreshTokenExpire": 720000,
    "iotToken": "f92203e0c7dee825312a6895996d0720",
    "refreshToken": "8813CBF0A9533838536738612D6ECA75",
    "iotTokenExpire": 72000
  },
  "id": "32dba207-99ac-4402-b9c7-98a28040fc80"
}
// get devices / mowers
https://ap-southeast-1.api-iot.aliyuncs.com/uc/listBindingByAccount?x-ca-request-id=e07b73b0-b517-4712-9d61-ba9556f2fb72
proto body? Gets devices plus iotId used elsewhere
https://ap-southeast-1.api-iot.aliyuncs.com/uc/listBindingByDev?x-ca-request-id=9b4ccede-fe8f-4513-8c5e-ef30056f6a65
proto body? gets singluar iotId device
https://ap-southeast-1.api-iot.aliyuncs.com/thing/properties/get?x-ca-request-id=00678145-b119-449d-a38c-07b29e3c46ce
proto body? gets properties on luba
https://ap-southeast-1.api-iot.aliyuncs.com/thing/service/invoke?x-ca-request-id=93abcc33-0826-4585-b4a1-f1c59c26e511
I think this sends normal protobuf messages to Luba e.g mow
