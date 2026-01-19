import { WikiSection, CopyablePrompt, QuickAnswer } from '../'

export default function RemoteAccessContent() {
  return (
    <div className="space-y-8">
      {/* Security Notice */}
      <div className="bg-rose-500/10 border border-rose-500/30 rounded-lg p-4">
        <div className="flex items-start space-x-3">
          <svg className="w-5 h-5 text-rose-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
          <div>
            <h4 className="text-sm font-medium text-rose-300">Security Notice</h4>
            <p className="text-sm text-gray-400 mt-1">
              Remote access means your RalphX instance can be reached from outside your home network.
              This is convenient but requires careful security setup. Follow the recommendations below.
            </p>
          </div>
        </div>
      </div>

      {/* Tailscale */}
      <WikiSection
        id="tailscale"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9" />
          </svg>
        }
        title="Option 1: Tailscale (Recommended)"
        description="Simple, secure VPN that just works"
      >
        <div className="space-y-4">
          <p className="text-gray-400 text-sm">
            Tailscale creates a private network between your devices. It's the easiest way to securely
            access RalphX from your phone or another computer. No port forwarding or complex setup required.
          </p>

          <CopyablePrompt
            title="Set up Tailscale"
            description="Walks you through installing Tailscale and configuring secure access."
            prompt={`Help me set up Tailscale so I can access RalphX from my phone.
Walk me through each step, enable MFA on my Tailscale account,
and verify it's working securely.`}
          />

          <div className="bg-cyan-500/10 border border-cyan-500/30 rounded-lg p-4">
            <h4 className="text-sm font-medium text-cyan-300 mb-2">Security Tips for Tailscale</h4>
            <ul className="text-sm text-gray-400 space-y-2">
              <li className="flex items-start space-x-2">
                <svg className="w-4 h-4 text-cyan-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <span><strong>Enable MFA</strong> on your Tailscale account (strongly recommended)</span>
              </li>
              <li className="flex items-start space-x-2">
                <svg className="w-4 h-4 text-cyan-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <span>By default, all your devices can connect - that's usually fine for personal use</span>
              </li>
              <li className="flex items-start space-x-2">
                <svg className="w-4 h-4 text-cyan-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <span>If you have many devices, consider ACLs to limit which can access RalphX</span>
              </li>
            </ul>
          </div>
        </div>
      </WikiSection>

      {/* Cloudflare Tunnel */}
      <WikiSection
        id="cloudflare"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z" />
          </svg>
        }
        title="Option 2: Cloudflare Tunnel"
        description="Custom domain with enterprise-grade security"
      >
        <div className="space-y-4">
          <p className="text-gray-400 text-sm">
            Cloudflare Tunnel lets you access RalphX via a custom domain (like ralph.yourdomain.com).
            Requires a domain name and more setup, but provides additional security features.
          </p>

          <CopyablePrompt
            title="Set up Cloudflare Tunnel"
            description="Configures a Cloudflare Tunnel with authentication so only you can access it."
            prompt={`Help me set up a Cloudflare Tunnel for RalphX with authentication
so only I can access it. Ask me about my domain, set up the tunnel,
AND configure Cloudflare Access so I need to log in to reach it.`}
          />

          <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-4">
            <h4 className="text-sm font-medium text-amber-300 mb-2">Security Tips for Cloudflare</h4>
            <ul className="text-sm text-gray-400 space-y-2">
              <li className="flex items-start space-x-2">
                <svg className="w-4 h-4 text-amber-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <span><strong>ALWAYS set up Cloudflare Access</strong> - without it, anyone with your URL can access RalphX</span>
              </li>
              <li className="flex items-start space-x-2">
                <svg className="w-4 h-4 text-amber-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <span>Use your email as the only allowed login</span>
              </li>
              <li className="flex items-start space-x-2">
                <svg className="w-4 h-4 text-amber-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <span>The prompt above includes auth setup - don't skip it</span>
              </li>
            </ul>
          </div>
        </div>
      </WikiSection>

      {/* Verification */}
      <WikiSection
        id="verify"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
        }
        title="Verify Your Setup"
        description="Make sure everything is secure"
      >
        <div className="space-y-4">
          <CopyablePrompt
            title="Verify remote access security"
            description="Checks that your remote access setup is working and properly secured."
            prompt={`Check if my remote access setup is working correctly and securely.
Verify I need to authenticate to access RalphX remotely.`}
          />
        </div>
      </WikiSection>

      {/* FAQ */}
      <WikiSection
        id="remote-faq"
        icon={
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        }
        title="Remote Access FAQ"
      >
        <div className="space-y-3">
          <QuickAnswer question="Which option should I choose?">
            <strong>Choose Tailscale</strong> if you want the simplest setup with excellent security.
            It works great for personal use and requires no domain name.
            <br /><br />
            <strong>Choose Cloudflare</strong> if you want a custom domain (like ralph.yourdomain.com)
            or need enterprise-grade access controls.
          </QuickAnswer>

          <QuickAnswer question="Is remote access safe?">
            Both options are secure when set up correctly. The key is authentication - make sure
            you need to log in to access RalphX. Never expose RalphX directly to the internet
            without authentication.
          </QuickAnswer>

          <QuickAnswer question="Can I use both Tailscale and Cloudflare?">
            Yes! Some users use Tailscale for personal devices and Cloudflare for sharing with team members.
            The setups don't conflict.
          </QuickAnswer>

          <QuickAnswer question="What if I don't need remote access?">
            That's fine! RalphX works perfectly fine on localhost. Remote access is optional
            and only needed if you want to monitor workflows from your phone or another location.
          </QuickAnswer>
        </div>
      </WikiSection>
    </div>
  )
}
