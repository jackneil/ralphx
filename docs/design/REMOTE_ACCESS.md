# Secure Remote Access to RalphX

## User Requirements

**Request**: Access RalphX from phone over the internet while away from home.

**Constraints**:
- Must be secure (not exposing the server to the open internet)
- Must be simple (no overkill solutions)
- Must be consistent (same URL/access method every time)

---

## Current State

- RalphX runs locally on `localhost:16768`
- Started with `./dev.sh`
- Only accessible from the local machine

---

## Options Analyzed

| Option | Setup Time | Security | Consistent URL | Free | Complexity |
|--------|-----------|----------|----------------|------|------------|
| **Tailscale** | ~5 min | Excellent (WireGuard) | Yes | Yes | Very Low |
| Cloudflare Tunnel | ~15 min | Excellent | Yes | Yes | Medium |
| ngrok | ~2 min | Good | No (paid for stable) | Limited | Low |
| WireGuard (manual) | 30+ min | Excellent | Yes | Yes | High |
| Port forward + DDNS | 1+ hour | Risky | Maybe | Yes | High |

### Option Details

**Tailscale**
- Creates a private mesh VPN using WireGuard
- Install on server + phone, both join your private network
- Server gets stable IP like `100.x.x.x`
- No ports exposed to public internet
- Free for personal use (up to 100 devices)

**Cloudflare Tunnel**
- Routes traffic through Cloudflare's network
- Can provide real HTTPS domain (e.g., `ralph.mydomain.com`)
- Includes DDoS protection and optional auth
- Requires cloudflared daemon running

**ngrok**
- Quick tunneling for development
- Free tier gives random URLs that change on restart
- Paid tier ($8/mo) for stable URLs
- Not ideal for "consistent" access requirement

**WireGuard (manual)**
- Same tech as Tailscale but self-managed
- Need to handle key generation, config files, port forwarding
- More control but significantly more setup

**Port forwarding + Dynamic DNS**
- Traditional approach: open port on router, use DDNS for changing IP
- Exposes your IP to the internet
- Need to handle HTTPS certificates yourself
- Security burden entirely on you

---

## Recommendation: Tailscale

**Reasoning**:
1. **Simplest setup**: Two installs, one login, done
2. **Most secure**: WireGuard encryption, zero exposed ports
3. **Meets all requirements**: Secure, simple, consistent
4. **No code changes**: RalphX works as-is
5. **Free**: No cost for personal use

---

## Implementation

### Step 1: Install Tailscale on Linux server

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Opens browser to authenticate (Google, GitHub, etc.)

### Step 2: Install Tailscale on phone

- iOS: App Store → "Tailscale"
- Android: Play Store → "Tailscale"

Sign in with same account.

### Step 3: Get server's Tailscale IP

```bash
tailscale ip -4
# Example: 100.64.0.1
```

### Step 4: Access from phone

Open browser: `http://100.64.0.1:16768`

---

## Security Model

- All traffic encrypted end-to-end (WireGuard protocol)
- No ports exposed to public internet
- Only devices authenticated to YOUR Tailscale account can connect
- Device access can be revoked from admin console
- Optional: Enable MFA on Tailscale account for extra security

---

## Alternative: Cloudflare Tunnel

Use if you want a real HTTPS domain like `ralph.yourdomain.com`:

1. Sign up for Cloudflare (free)
2. Add your domain to Cloudflare
3. Install cloudflared: `sudo apt install cloudflared`
4. Authenticate: `cloudflared tunnel login`
5. Create tunnel: `cloudflared tunnel create ralph`
6. Configure tunnel to point to `localhost:16768`
7. Add DNS record pointing to tunnel
8. Optional: Add Cloudflare Access policy for login page

More complex but provides:
- Real HTTPS URL
- Works without VPN app on phone
- Can share access with others via email auth
