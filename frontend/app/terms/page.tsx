import Link from "next/link";

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-white">
      {/* Navigation */}
      <nav className="border-b border-slate-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-16 items-center justify-between">
            <Link href="/" className="flex items-center gap-2">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-blue-700 text-2xl font-bold text-white shadow-lg">
                S
              </div>
              <span className="text-xl font-bold text-slate-900">SuoOps</span>
            </Link>
            <Link
              href="/"
              className="text-sm font-medium text-slate-600 hover:text-slate-900"
            >
              ← Back to Home
            </Link>
          </div>
        </div>
      </nav>

      {/* Content */}
      <div className="mx-auto max-w-4xl px-4 py-16 sm:px-6 lg:px-8">
        <h1 className="text-4xl font-bold text-slate-900">Terms of Service</h1>
        <p className="mt-4 text-lg text-slate-600">
          Last updated: October 28, 2025
        </p>

        <div className="mt-12 space-y-8 text-slate-700">
          <section>
            <h2 className="text-2xl font-bold text-slate-900">1. Agreement to Terms</h2>
            <p className="mt-4">
              By accessing or using SuoOps (&quot;Service&quot;), you agree to be bound by these Terms of Service (&quot;Terms&quot;). If you do not agree to these Terms, you may not use our Service.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900">2. Description of Service</h2>
            <p className="mt-4">
              SuoOps is a WhatsApp-based invoice management platform that allows businesses to:
            </p>
            <ul className="mt-4 list-disc space-y-2 pl-6">
              <li>Create invoices via voice notes or text messages</li>
              <li>Send invoices to customers via WhatsApp</li>
              <li>Track invoice status and payments</li>
              <li>Generate PDF receipts and invoices</li>
              <li>Manage customer information and payment details</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900">3. Account Registration</h2>
            <p className="mt-4">To use SuoOps, you must:</p>
            <ul className="mt-4 list-disc space-y-2 pl-6">
              <li>Be at least 18 years old or the age of majority in your jurisdiction</li>
              <li>Provide accurate, complete, and current information</li>
              <li>Maintain the security of your account credentials</li>
              <li>Notify us immediately of any unauthorized access</li>
              <li>Be responsible for all activities under your account</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900">4. Subscription Plans</h2>
            <p className="mt-4">SuoOps offers the following subscription plans:</p>
            <ul className="mt-4 list-disc space-y-2 pl-6">
              <li><strong>Free Plan:</strong> 5 invoices per month at no cost</li>
              <li><strong>Starter Plan:</strong> 100 invoices per month for ₦2,500/month</li>
              <li><strong>Pro Plan:</strong> 1,000 invoices per month for ₦7,500/month</li>
              <li><strong>Business Plan:</strong> 3,000 invoices per month for ₦15,000/month</li>
            </ul>
            <p className="mt-4">
              Prices are in Nigerian Naira (₦) and subject to change with 30 days&apos; notice. Subscriptions renew automatically unless cancelled.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900">5. Payment Terms</h2>
            <p className="mt-4">
              Subscription payments are processed securely through Paystack. By subscribing, you authorize us to charge your payment method on a recurring basis. We do not store your card details.
            </p>
            <p className="mt-4">
              <strong>Refund Policy:</strong> We offer a 7-day money-back guarantee for first-time subscribers. After 7 days, subscription fees are non-refundable. You may cancel at any time to prevent future charges.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900">6. Acceptable Use</h2>
            <p className="mt-4">You agree NOT to:</p>
            <ul className="mt-4 list-disc space-y-2 pl-6">
              <li>Use the Service for any illegal or fraudulent purpose</li>
              <li>Send spam or unsolicited messages to customers</li>
              <li>Create fake or fraudulent invoices</li>
              <li>Violate any applicable laws or regulations</li>
              <li>Interfere with or disrupt the Service</li>
              <li>Attempt to access unauthorized areas or data</li>
              <li>Use the Service to harass, abuse, or harm others</li>
              <li>Impersonate any person or entity</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900">7. Invoice Payments</h2>
            <p className="mt-4">
              <strong>Important:</strong> SuoOps is NOT a payment processor. We facilitate invoice delivery via WhatsApp, but:
            </p>
            <ul className="mt-4 list-disc space-y-2 pl-6">
              <li>Customers pay directly to your bank account</li>
              <li>We do NOT hold, process, or guarantee payments</li>
              <li>You are responsible for verifying and confirming payments</li>
              <li>Disputes between you and your customers are your responsibility</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900">8. WhatsApp Integration</h2>
            <p className="mt-4">
              Our Service uses WhatsApp Cloud API (Meta). By using SuoOps, you also agree to WhatsApp&apos;s Business Terms and Meta&apos;s Terms of Service. We are not responsible for WhatsApp&apos;s availability or any changes to their API.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900">9. Intellectual Property</h2>
            <p className="mt-4">
              SuoOps and its content (including software, design, text, and logos) are owned by us and protected by copyright, trademark, and other intellectual property laws. You may not copy, modify, distribute, or reverse engineer our Service.
            </p>
            <p className="mt-4">
              You retain ownership of your data (invoices, customer information, etc.). By using our Service, you grant us a license to process and display your data as necessary to provide the Service.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900">10. Service Availability</h2>
            <p className="mt-4">
              We strive to maintain high availability but do not guarantee uninterrupted access. The Service may be temporarily unavailable due to:
            </p>
            <ul className="mt-4 list-disc space-y-2 pl-6">
              <li>Scheduled maintenance</li>
              <li>Technical issues or emergencies</li>
              <li>Third-party service outages (WhatsApp, AWS, etc.)</li>
              <li>Force majeure events</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900">11. Limitation of Liability</h2>
            <p className="mt-4">
              TO THE MAXIMUM EXTENT PERMITTED BY LAW, SUOOPS SHALL NOT BE LIABLE FOR:
            </p>
            <ul className="mt-4 list-disc space-y-2 pl-6">
              <li>Any indirect, incidental, or consequential damages</li>
              <li>Loss of profits, revenue, or data</li>
              <li>Customer disputes or payment issues</li>
              <li>WhatsApp delivery failures</li>
              <li>Any damages exceeding the amount you paid in the past 12 months</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900">12. Indemnification</h2>
            <p className="mt-4">
              You agree to indemnify and hold harmless SuoOps from any claims, damages, or expenses arising from your use of the Service, violation of these Terms, or infringement of any rights of others.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900">13. Termination</h2>
            <p className="mt-4">
              We may suspend or terminate your account at any time for:
            </p>
            <ul className="mt-4 list-disc space-y-2 pl-6">
              <li>Violation of these Terms</li>
              <li>Fraudulent or illegal activity</li>
              <li>Non-payment of subscription fees</li>
              <li>Extended inactivity (free accounts only)</li>
            </ul>
            <p className="mt-4">
              You may cancel your subscription at any time from your dashboard. Upon termination, you will lose access to your data after 30 days unless you export it.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900">14. Governing Law</h2>
            <p className="mt-4">
              These Terms are governed by the laws of the Federal Republic of Nigeria. Any disputes shall be resolved in the courts of Lagos, Nigeria.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900">15. Changes to Terms</h2>
            <p className="mt-4">
              We may update these Terms from time to time. We will notify you of significant changes via email or through the Service. Continued use after changes constitutes acceptance of the new Terms.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-bold text-slate-900">16. Contact Information</h2>
            <p className="mt-4">
              For questions about these Terms, contact us:
            </p>
            <ul className="mt-4 space-y-2">
              <li>
                <strong>Email:</strong>{" "}
                <a href="mailto:info@suoops.com" className="text-blue-600 hover:underline">
                  info@suoops.com
                </a>
              </li>
              <li>
                <strong>Website:</strong>{" "}
                <a href="https://suoops.com" className="text-blue-600 hover:underline">
                  https://suoops.com
                </a>
              </li>
            </ul>
          </section>

          <section className="rounded-lg bg-blue-50 p-6">
            <h3 className="text-lg font-bold text-slate-900">Quick Summary</h3>
            <p className="mt-2 text-sm">
              By using SuoOps, you agree to: (1) Use the Service responsibly and legally, (2) Pay subscription fees on time, (3) Verify customer payments yourself, (4) Not hold us liable for payment disputes or WhatsApp issues, and (5) Accept that we may update these Terms with notice.
            </p>
          </section>
        </div>

        <div className="mt-12 border-t border-slate-200 pt-8 text-center">
          <Link
            href="/"
            className="inline-flex items-center gap-2 text-blue-600 hover:text-blue-700"
          >
            ← Back to Home
          </Link>
        </div>
      </div>
    </div>
  );
}
