#!/usr/bin/env python3
"""Test Imobiliare.ro scraping with stealth."""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from playwright.async_api import async_playwright

async def test_imobiliare_stealth():
    """Test scraping Imobiliare.ro with stealth mode."""
    print("🕵️  Testing Imobiliare.ro with stealth...")
    print("="*60)
    
    url = "https://www.imobiliare.ro/vanzare-case-vile/bucuresti?pretmax=200000"
    
    async with async_playwright() as p:
        # Launch with maximum stealth
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu',
                '--window-size=1920,1080',
            ]
        )
        
        # Create context with realistic settings
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='Europe/Bucharest',
            geolocation={'latitude': 44.4268, 'longitude': 26.1025},  # Bucharest
            permissions=['geolocation'],
            color_scheme='light',
        )
        
        # Add stealth scripts
        await context.add_init_script("""
            // Override navigator properties
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            
            Object.defineProperty(navigator, 'languages', {
                get: () => ['en-US', 'en', 'ro']
            });
            
            // Override permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' 
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters)
            );
            
            // Hide Chrome runtime
            window.chrome = {
                runtime: {
                    OnInstalledReason: {
                        CHROME_UPDATE: "chrome_update",
                        INSTALL: "install",
                        SHARED_MODULE_UPDATE: "shared_module_update",
                        UPDATE: "update"
                    },
                    OnRestartRequiredReason: {
                        APP_UPDATE: "app_update",
                        OS_UPDATE: "os_update",
                        PERIODIC: "periodic"
                    },
                    PlatformArch: {
                        ARM: "arm",
                        ARM64: "arm64",
                        MIPS: "mips",
                        MIPS64: "mips64",
                        MIPS64EL: "mips64el",
                        MIPSEL: "mipsel",
                        X86_32: "x86-32",
                        X86_64: "x86-64"
                    },
                    PlatformNaclArch: {
                        ARM: "arm",
                        MIPS: "mips",
                        MIPS64: "mips64",
                        MIPS64EL: "mips64el",
                        MIPSEL: "mipsel",
                        MIPSEL64: "mipsel64",
                        X86_32: "x86-32",
                        X86_64: "x86-64"
                    },
                    PlatformOs: {
                        ANDROID: "android",
                        CROS: "cros",
                        LINUX: "linux",
                        MAC: "mac",
                        OPENBSD: "openbsd",
                        WIN: "win"
                    },
                    RequestUpdateCheckStatus: {
                        NO_UPDATE: "no_update",
                        THROTTLED: "throttled",
                        UPDATE_AVAILABLE: "update_available"
                    }
                }
            };
            
            // Override webgl
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) {
                    return 'Intel Inc.';
                }
                if (parameter === 37446) {
                    return 'Intel Iris OpenGL Engine';
                }
                return getParameter(parameter);
            };
        """)
        
        page = await context.new_page()
        
        try:
            print(f"🌐 Navigating to: {url}")
            
            # Navigate with extra wait
            response = await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            print(f"📊 Response status: {response.status if response else 'N/A'}")
            
            # Wait a bit for any JS redirects
            await asyncio.sleep(3)
            
            # Get current URL
            current_url = page.url
            print(f"🔗 Current URL: {current_url}")
            
            # Check for CAPTCHA indicators
            page_content = await page.content()
            
            if 'cf-browser-verification' in page_content or 'Checking your browser' in page_content:
                print("❌ Cloudflare CAPTCHA detected!")
            elif 'Please enable JS' in page_content or 'Please enable JavaScript' in page_content:
                print("❌ JavaScript check detected!")
            elif 'imobiliare' not in current_url.lower():
                print(f"❌ Redirected away: {current_url}")
            else:
                print("✅ Page loaded successfully!")
                
                # Try to find listings
                try:
                    # Wait for content to load
                    await page.wait_for_load_state('networkidle')
                    await asyncio.sleep(2)
                    
                    # Try different selectors
                    selectors = [
                        '.box-anunt',
                        '[data-testid="listing-card"]',
                        '.listing-item',
                        'article',
                        '.property-card'
                    ]
                    
                    for selector in selectors:
                        try:
                            await page.wait_for_selector(selector, timeout=5000)
                            cards = await page.query_selector_all(selector)
                            print(f"✅ Found {len(cards)} listings with selector: {selector}")
                            
                            if cards:
                                # Show first listing
                                first = cards[0]
                                title = await first.inner_text()
                                print(f"\n📍 First listing preview:")
                                print(f"   {title[:100]}...")
                                break
                        except:
                            continue
                    else:
                        print("⚠️  No listings found with any selector")
                        print("\n🔍 Page title:", await page.title())
                        
                except Exception as e:
                    print(f"⚠️  Error finding listings: {e}")
            
            # Save screenshot for debugging
            screenshot_path = '/tmp/imobiliare_test.png'
            await page.screenshot(path=screenshot_path, full_page=True)
            print(f"\n📸 Screenshot saved: {screenshot_path}")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
        
        finally:
            await browser.close()
    
    print("\n" + "="*60)
    print("Test complete!")

if __name__ == '__main__':
    asyncio.run(test_imobiliare_stealth())
