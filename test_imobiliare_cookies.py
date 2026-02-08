#!/usr/bin/env python3
"""Test Imobiliare.ro scraping with user's cookies."""

import httpx
import re
import json
from datetime import datetime, timezone

# Cookies from user (Netscape format converted)
COOKIES = {
    'imovzt': '5502830201',
    'imo_visitor_id_cookie': 'imo_visitor_id_cookie-2d141d8b-44c4-484a-85c5-f87a41ff5aa0',
    'OptanonAlertBoxClosed': '2025-12-29T08:27:31.578Z',
    'eupubconsent-v2': 'CQdMJPAQdMJPAAcABBROCLF8AP_gAEPgAChQKVtR3G__bWlr-Tb3afpkeYxP99hr7sQxBgbJk24FzLvW7JwSx2ExNAzatqIKmRIAu3TBIQNlGJDURVCgKIgFrSDMaEiUoTNKJ6BkiBMRI2JYCFxvmwpjWQCY4vr99lcxmB-N7dr82dzyy4BHn3a5_2S1UJCdIYetDfn8ZBKT-9IEd_x8v4v4_F7pE2-eS1l_pGvp4j9-YlM_dBGxt-TSfbzPn_frk_eClAAJhoVEEZZEAAQKBgBAgAUFYQAUCAIAAEgaICAEwYFOQMAF1hMgBACgAGCAEAAIMAAQAACQAIRABQAQCAECAQKAAIACAICABgYAAwAWIgEAAIDoEKYEEAgWACRmVQaYEIACQQEtlQgkAQIK4QhFngEECImCgAABAAKAAAAeCwEJJASsSCALiCaAAAgAACCBAgRSFmAIKAzRaCsCTgMjSAMHzBMkp0AA.f_wACHwAAAAA',
    '_gcl_au': '1.1.67342866.1769864145',
    '_cq_duid': '1.1769864148.b3U0eDSk4ETuTcGQ',
    '__cf_bm': 'LSJtAWe_En4fdlyUl8dAxC6XIICV.bwUnViKCkf2M5M-1770564953-1.0.1.1-LVePE6UsV3qYbnQZPefFH5_ugVYGOMP2ri1me.vfE4udXkYRhm9I4xYDAeQJMpDA9MWdrEzxcWQCWHQdRH_xJB5D5wQLePISwk1dBaSdZ64',
    'datadome': 'l8h_uDVBF3Afoi~VxaIK7NGiRe9Wk5ggZgUBTL6gKpAo6LIOgFA7TwbSqqyKySs5S4X0c3zv_NryjUUE8BwHNudzyy~6llhVUDG8qWDGa~CayKKC9sbfWeCDkryY_Zp3',
}

# Headers matching a real browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9,ro;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    'Sec-Ch-Ua': '"Not A(Brand";v="8", "Chromium";v="132"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
    'Referer': 'https://www.imobiliare.ro/',
}

async def test_imobiliare_with_cookies():
    """Test scraping with user's cookies."""
    print("🍪 Testing Imobiliare.ro with user cookies...")
    print("="*60)
    
    url = "https://www.imobiliare.ro/vanzare-case-vile/bucuresti?pretmax=200000"
    
    async with httpx.AsyncClient(
        headers=HEADERS,
        cookies=COOKIES,
        follow_redirects=True,
        timeout=30.0
    ) as client:
        try:
            print(f"🌐 Fetching: {url}")
            response = await client.get(url)
            
            print(f"📊 Status: {response.status_code}")
            print(f"🔗 Final URL: {response.url}")
            print(f"📄 Content length: {len(response.text):,} bytes")
            
            # Check if we got real content or CAPTCHA
            html = response.text
            
            if 'captcha' in html.lower() or 'datadome' in html.lower():
                print("❌ CAPTCHA/DataDome still detected!")
                return None
            
            if 'box-anunt' in html or 'listing' in html.lower():
                print("✅ Listing content found!")
                
                # Try to extract listing count
                # Look for common patterns
                patterns = [
                    r'(\d+)\s+anunturi',
                    r'(\d+)\s+proprietati',
                    r'(\d+)\s+rezultate',
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, html, re.IGNORECASE)
                    if matches:
                        print(f"📊 Found {matches[0]} listings mentioned")
                        break
                
                # Look for property cards
                if 'box-anunt' in html:
                    # Count property cards
                    cards = re.findall(r'class="[^"]*box-anunt[^"]*"', html)
                    print(f"📦 Found {len(cards)} property card divs")
                
                return html
            else:
                print("⚠️  No listing content found")
                # Save first 2000 chars to debug
                print("\n🔍 HTML preview (first 1000 chars):")
                print(html[:1000])
                return None
                
        except Exception as e:
            print(f"❌ Error: {e}")
            return None

async def test_single_page():
    """Test a single property page."""
    print("\n" + "="*60)
    print("🏠 Testing single property page...")
    print("="*60)
    
    # Test URL - a known listing
    url = "https://www.imobiliare.ro/vanzare-casa/vila/bucuresti/bucuresti-ilfov/anunt-EXAMPLE123"
    
    async with httpx.AsyncClient(
        headers=HEADERS,
        cookies=COOKIES,
        follow_redirects=True,
        timeout=30.0
    ) as client:
        try:
            response = await client.get(url)
            print(f"📊 Status: {response.status_code}")
            
            if response.status_code == 200:
                print("✅ Single page accessible!")
            else:
                print(f"❌ Page returned {response.status_code}")
                
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == '__main__':
    import asyncio
    
    html = asyncio.run(test_imobiliare_with_cookies())
    
    if html:
        print("\n" + "="*60)
        print("🎉 SUCCESS! Cookies work for Imobiliare.ro")
        print("="*60)
        
        # Save to file for inspection
        with open('/tmp/imobiliare_cookies_test.html', 'w') as f:
            f.write(html)
        print("💾 HTML saved to /tmp/imobiliare_cookies_test.html")
    else:
        print("\n" + "="*60)
        print("❌ FAILED - Cookies didn't bypass protection")
        print("="*60)
        print("\nPosibile cauze:")
        print("1. Cookie-urile au expirat (datadome e sesiune scurtă)")
        print("2. IP-ul VPS e blacklisted separat de cookies")
        print("3. Alte headers necesare (fingerprinting)")
        print("\nSolutie: Residential proxy sau CapSolver")
