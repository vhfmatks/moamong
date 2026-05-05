# Keyword Lookup API Notes

This document summarizes keyword lookup endpoints observed from the UKEY app traffic and direct CLI checks.

Generated on: 2026-05-05

## Summary

| Site | Endpoint | Auth required | Method | Result type | Notes |
|---|---|---:|---|---|---|
| 11st | `https://apis.11st.co.kr/search/api/tab?kwd={keyword}&tabId=TOTAL_SEARCH` | No | `GET` | Related keywords, recommended products, search metadata | Direct CLI request returned `200 OK`. |
| Gmarket | `https://frontapi.gmarket.co.kr/autocompleteV2/kr/json/{keyword}` | No | `GET` | Autocomplete keywords | Direct CLI request returned `200 OK`. |
| Auction | `https://suggest.auction.co.kr/Suggest/SuggestWebService.asmx` | No | `POST` SOAP | Suggested keywords | Requires SOAP XML body with `keywordHint`. |
| Naver autocomplete | `https://ac.search.naver.com/nx/ac?q={keyword}&st=100&r_format=json&r_enc=UTF-8&r_unicode=0&q_enc=UTF-8` | No | `GET` | Autocomplete keywords | Direct CLI request returned `200 OK`. |
| Naver Shopping OpenAPI | `https://openapi.naver.com/v1/search/shop.json?query={keyword}` | Yes | `GET` | Shopping search | Requires `X-Naver-Client-Id` and `X-Naver-Client-Secret`. |
| Naver SearchAd | `https://api.searchad.naver.com/keywordstool?hintKeywords={keyword}&includeHintKeywords=1&showDetail=1` | Yes | `GET` | Keyword metrics | Requires `X-API-KEY`, `X-Customer`, `X-Timestamp`, and `X-Signature`. |
| Coupang | `https://www.coupang.com/np/search/autoComplete?keyword={keyword}` | Session/cookie in practice | `GET` | Autocomplete keywords | Direct CLI request without browser session returned `403 Access Denied`. |

## PowerShell Examples

The examples below use `버터` as the keyword.

### 11st

```powershell
Invoke-RestMethod `
  -Uri 'https://apis.11st.co.kr/search/api/tab?kwd=%EB%B2%84%ED%84%B0&tabId=TOTAL_SEARCH' `
  -Headers @{ Accept = 'application/json' }
```

Observed related keywords included:

```text
땅콩버터
기버터
무염버터
앵커버터
라꽁비에뜨버터
포션버터
가염버터
이즈니무염버터
에쉬레버터
프레지덩 버터
목초버터
목초기버터
밀키오 기버터
고메버터
목초우 기버터
```

### Gmarket

```powershell
Invoke-RestMethod `
  -Uri 'https://frontapi.gmarket.co.kr/autocompleteV2/kr/json/%EB%B2%84%ED%84%B0'
```

Observed autocomplete keywords included:

```text
버터
버터와플
버터떡
버터와플 이즈니
버터구이오징어
버터링
버터쿠키
버터플라이 탁구복
버터 10g
버터쿠키 대용량
```

### Auction

```powershell
$body = "<?xml version='1.0' encoding='utf-8'?><soap:Envelope xmlns:xsi='http://www.w3.org/2001/XMLSchema-instance' xmlns:xsd='http://www.w3.org/2001/XMLSchema' xmlns:soap='http://schemas.xmlsoap.org/soap/envelope/'><soap:Body><GetKeywordSuggest xmlns='ns'><keywordHint>버터</keywordHint></GetKeywordSuggest></soap:Body></soap:Envelope>"

Invoke-WebRequest `
  -Uri 'https://suggest.auction.co.kr/Suggest/SuggestWebService.asmx' `
  -Method POST `
  -Headers @{ SOAPAction = '"ns/GetKeywordSuggest"' } `
  -ContentType 'text/xml; charset=utf-8' `
  -Body $body `
  -UseBasicParsing
```

Observed suggested keywords included:

```text
버터
땅콩버터
스키피 땅콩버터
차량용 인버터
라꽁비에뜨 버터
아몬드버터
버터링
무염버터
인버터
버터떡
```

### Naver Autocomplete

```powershell
Invoke-RestMethod `
  -Uri 'https://ac.search.naver.com/nx/ac?q=%EB%B2%84%ED%84%B0&st=100&r_format=json&r_enc=UTF-8&r_unicode=0&q_enc=UTF-8' `
  -Headers @{ 'User-Agent' = 'Mozilla/5.0'; Referer = 'https://www.naver.com/' }
```

Observed autocomplete keywords included:

```text
버터떡
버터떡 레시피
버터
버터 효능
버터 추천
버터 다이어트
상하이 버터떡
버터샵
기버터
버터런
```

### Naver Shopping OpenAPI

This endpoint requires credentials issued by Naver.

```powershell
Invoke-RestMethod `
  -Uri 'https://openapi.naver.com/v1/search/shop.json?display=10&query=%EB%B2%84%ED%84%B0' `
  -Headers @{
    'X-Naver-Client-Id' = '<your-client-id>'
    'X-Naver-Client-Secret' = '<your-client-secret>'
  }
```

Without credentials, the observed response was:

```text
Status: 401
errorCode: 024
errorMessage: Not Exist Client ID : Authentication failed.
```

### Naver SearchAd Keyword Tool

This endpoint requires credentials issued for a Naver SearchAd account.

```powershell
Invoke-RestMethod `
  -Uri 'https://api.searchad.naver.com/keywordstool?hintKeywords=%EB%B2%84%ED%84%B0&includeHintKeywords=1&showDetail=1' `
  -Headers @{
    'X-API-KEY' = '<your-api-key>'
    'X-Customer' = '<your-customer-id>'
    'X-Timestamp' = '<timestamp-ms>'
    'X-Signature' = '<signature>'
  }
```

Without credentials, the observed response was:

```text
Status: 400
detail: HTTP header required: X-API-KEY
```

### Coupang

```powershell
Invoke-WebRequest `
  -Uri 'https://www.coupang.com/np/search/autoComplete?keyword=%EB%B2%84%ED%84%B0' `
  -Headers @{
    'User-Agent' = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/136.0.0.0 Safari/537.36'
    Accept = 'application/json,text/javascript,*/*;q=0.01'
    'X-Requested-With' = 'XMLHttpRequest'
    Referer = 'https://www.coupang.com/'
  } `
  -UseBasicParsing
```

Direct CLI request without a browser session returned:

```text
Status: 403
Access Denied
```

## Security Notes

- Do not commit captured traffic files that include secrets, cookies, API keys, or signatures.
- Use only API credentials issued to your own account.
- Avoid reusing credentials captured from another application process.
- Some endpoints are not public APIs and may change or block non-browser traffic.
