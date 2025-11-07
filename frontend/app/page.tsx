"use client";

import Link from "next/link";
import { useState } from "react";
import RegulatoryNotice from "@/components/regulatory-notice";

export default function HomePage() {
  const [showVideoModal, setShowVideoModal] = useState(false);

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-50 to-white">
      {/* Pre-Launch Banner */}
      <div className="bg-gradient-to-r from-yellow-400 via-orange-400 to-yellow-400 px-4 py-3 text-center">
        <p className="text-sm font-semibold text-slate-900">
          ⏳ <strong>Pre-Launch:</strong> Join our waitlist to get early access + exclusive 50% launch discount! 🚀
        </p>
      </div>

      {/* Regulatory / Accreditation Notice */}
      <div className="border-b border-blue-200 bg-blue-50 py-2 px-4">
        <RegulatoryNotice variant="general" />
      </div>

      {/* Navigation */}
      <nav className="border-b border-slate-200 bg-white/80 backdrop-blur-sm sticky top-0 z-50">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
          <div className="flex h-16 items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-blue-700 text-2xl font-bold text-white shadow-lg">
                S
              </div>
              <span className="text-xl font-bold text-slate-900">SuoOps</span>
            </div>
            <div className="flex items-center gap-4">
              <a
                href="https://docs.google.com/forms/d/e/1FAIpQLSc8s7K5WNC_6xDzg2IlUMJtxzvF4T18YwYlW_ruHMyC6IT5yg/viewform"
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm font-medium text-slate-600 hover:text-slate-900"
              >
                Join Waitlist
              </a>
              <Link
                href="/login"
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
              >
                Login
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative overflow-hidden px-4 py-20 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-7xl">
          <div className="grid gap-12 lg:grid-cols-2 lg:gap-8">
            <div className="flex flex-col justify-center">
              <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-orange-200 bg-orange-50 px-4 py-1.5 text-sm font-medium text-orange-700 w-fit">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-orange-400 opacity-75"></span>
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-orange-500"></span>
                </span>
                Coming Soon • Join Waitlist 🚀
              </div>
              <h1 className="text-5xl font-bold tracking-tight text-slate-900 sm:text-6xl lg:text-7xl">
                Invoice via
                <span className="bg-gradient-to-r from-blue-600 to-purple-600 bg-clip-text text-transparent">
                  {" "}
                  WhatsApp
                </span>
                <br />
                Get Paid Faster
              </h1>
              <p className="mt-6 text-lg text-slate-600 sm:text-xl">
                Create professional invoices by sending a voice note or text message on WhatsApp. 
                No apps to download, no complex software—just speak or type and get paid.
              </p>
              <div className="mt-8 flex flex-col gap-4 sm:flex-row">
                <a
                  href="https://docs.google.com/forms/d/e/1FAIpQLSc8s7K5WNC_6xDzg2IlUMJtxzvF4T18YwYlW_ruHMyC6IT5yg/viewform"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-blue-600 to-purple-600 px-8 py-4 text-center text-base font-semibold text-white shadow-lg hover:from-blue-700 hover:to-purple-700 transition-all hover:shadow-xl hover:scale-105"
                >
                  Join Waitlist - Get Early Access 🚀
                </a>
                <button
                  onClick={() => setShowVideoModal(true)}
                  className="rounded-lg border-2 border-slate-200 bg-white px-8 py-4 text-center text-base font-semibold text-slate-700 hover:border-slate-300 hover:bg-slate-50 transition-all"
                >
                  Watch Demo →
                </button>
              </div>
              <div className="mt-8 flex items-center gap-6 text-sm text-slate-500">
                <div className="flex items-center gap-2">
                  <svg className="h-5 w-5 text-green-500" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                  </svg>
                  50% launch discount
                </div>
                <div className="flex items-center gap-2">
                  <svg className="h-5 w-5 text-green-500" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                  </svg>
                  Priority early access
                </div>
              </div>
            </div>
            <div className="relative lg:mt-0">
              <div className="relative mx-auto max-w-md">
                {/* Phone Mockup */}
                <div className="relative rounded-[3rem] border-[14px] border-slate-900 bg-slate-900 shadow-2xl">
                  <div className="overflow-hidden rounded-[2.3rem] bg-white">
                    {/* Status Bar */}
                    <div className="bg-gradient-to-b from-emerald-500 to-emerald-600 px-6 py-3">
                      <div className="flex items-center justify-between text-white">
                        <span className="text-xs font-medium">9:41</span>
                        <div className="flex gap-1">
                          <div className="h-3 w-3 rounded-full border border-white"></div>
                          <div className="h-3 w-3 rounded-full border border-white"></div>
                          <div className="h-3 w-3 rounded-full border border-white"></div>
                        </div>
                      </div>
                    </div>
                    {/* WhatsApp Header */}
                    <div className="bg-emerald-600 px-6 py-4 text-white">
                      <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-full bg-slate-300"></div>
                        <div>
                          <p className="font-semibold">SuoOps Bot</p>
                          <p className="text-xs opacity-90">online</p>
                        </div>
                      </div>
                    </div>
                    {/* Chat Messages */}
                    <div className="bg-[#efeae2] px-4 py-6 space-y-3 min-h-[400px]">
                      {/* Incoming Message */}
                      <div className="flex justify-start">
                        <div className="max-w-[80%] rounded-lg bg-white px-4 py-2 shadow-sm">
                          <p className="text-sm text-slate-800">👋 Hi! Send me a voice note to create an invoice.</p>
                          <p className="mt-1 text-xs text-slate-500">9:40 AM</p>
                        </div>
                      </div>
                      {/* Voice Note */}
                      <div className="flex justify-end">
                        <div className="max-w-[80%] rounded-lg bg-emerald-100 px-4 py-3 shadow-sm">
                          <div className="flex items-center gap-2">
                            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-emerald-500 text-white">
                              <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
                                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clipRule="evenodd" />
                              </svg>
                            </div>
                            <div className="flex-1">
                              <div className="h-1 w-full rounded-full bg-emerald-300">
                                <div className="h-1 w-3/4 rounded-full bg-emerald-600"></div>
                              </div>
                              <p className="mt-1 text-xs text-slate-600">0:15</p>
                            </div>
                          </div>
                          <p className="mt-2 text-xs text-slate-600 italic">
                            &quot;Invoice Jane fifty thousand naira for logo design&quot;
                          </p>
                        </div>
                      </div>
                      {/* Bot Response */}
                      <div className="flex justify-start">
                        <div className="max-w-[80%] rounded-lg bg-white px-4 py-3 shadow-sm">
                          <p className="text-sm font-semibold text-slate-800">✅ Invoice Created!</p>
                          <div className="mt-2 space-y-1 text-sm text-slate-600">
                            <p>📄 ID: INV-2024-001</p>
                            <p>👤 Customer: Jane</p>
                            <p>💰 Amount: ₦50,000</p>
                          </div>
                          <button className="mt-3 w-full rounded-lg bg-blue-600 py-2 text-sm font-semibold text-white">
                            View Invoice →
                          </button>
                          <p className="mt-2 text-xs text-slate-500">9:41 AM</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                {/* Decorative Elements */}
                <div className="absolute -right-4 -top-4 h-24 w-24 rounded-full bg-blue-100 opacity-50 blur-2xl"></div>
                <div className="absolute -bottom-4 -left-4 h-32 w-32 rounded-full bg-purple-100 opacity-50 blur-2xl"></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Waitlist Counter */}
      <section className="border-y border-slate-200 bg-white px-4 py-12 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-7xl text-center">
          <div className="inline-flex items-center gap-4 rounded-2xl border-2 border-blue-200 bg-blue-50 px-8 py-6">
            <div className="text-left">
              <p className="text-4xl font-bold text-blue-600">50+</p>
              <p className="text-sm font-medium text-slate-600">Businesses Waiting</p>
            </div>
            <div className="h-16 w-px bg-blue-200"></div>
            <div className="text-left">
              <p className="text-sm font-semibold text-slate-900">Join the waitlist today</p>
              <p className="text-xs text-slate-600">Limited early access spots</p>
            </div>
            <a
              href="https://docs.google.com/forms/d/e/1FAIpQLSc8s7K5WNC_6xDzg2IlUMJtxzvF4T18YwYlW_ruHMyC6IT5yg/viewform"
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-lg bg-blue-600 px-6 py-3 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
            >
              Join Now →
            </a>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="px-4 py-20 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-7xl">
          <div className="text-center">
            <h2 className="text-base font-semibold text-blue-600">HOW IT WORKS</h2>
            <p className="mt-2 text-4xl font-bold text-slate-900 sm:text-5xl">
              Simple as sending a message
            </p>
            <p className="mt-4 text-lg text-slate-600">
              No apps, no training, no hassle. Just WhatsApp—use voice notes or text messages.
            </p>
          </div>

          <div className="mt-16 grid gap-8 md:grid-cols-3">
            {/* Step 1 */}
            <div className="relative rounded-2xl border border-slate-200 bg-white p-8 shadow-sm hover:shadow-lg transition-shadow">
              <div className="absolute -top-4 left-8 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-blue-700 text-xl font-bold text-white shadow-lg">
                1
              </div>
              <div className="mt-8 flex h-16 w-16 items-center justify-center rounded-2xl bg-blue-100 text-3xl">
                🎤
              </div>
              <h3 className="mt-6 text-xl font-bold text-slate-900">Send Voice or Text</h3>
              <p className="mt-2 text-slate-600">
                Open WhatsApp and send a voice note or text: &quot;Invoice John 25,000 naira for consultation&quot;
              </p>
            </div>

            {/* Step 2 */}
            <div className="relative rounded-2xl border border-slate-200 bg-white p-8 shadow-sm hover:shadow-lg transition-shadow">
              <div className="absolute -top-4 left-8 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-purple-600 to-purple-700 text-xl font-bold text-white shadow-lg">
                2
              </div>
              <div className="mt-8 flex h-16 w-16 items-center justify-center rounded-2xl bg-purple-100 text-3xl">
                ⚡
              </div>
              <h3 className="mt-6 text-xl font-bold text-slate-900">AI Creates Invoice</h3>
              <p className="mt-2 text-slate-600">
                Our AI instantly understands your voice and generates a professional invoice with payment details
              </p>
            </div>

            {/* Step 3 */}
            <div className="relative rounded-2xl border border-slate-200 bg-white p-8 shadow-sm hover:shadow-lg transition-shadow">
              <div className="absolute -top-4 left-8 flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-green-600 to-green-700 text-xl font-bold text-white shadow-lg">
                3
              </div>
              <div className="mt-8 flex h-16 w-16 items-center justify-center rounded-2xl bg-green-100 text-3xl">
                💸
              </div>
              <h3 className="mt-6 text-xl font-bold text-slate-900">Get Paid</h3>
              <p className="mt-2 text-slate-600">
                Customer receives invoice via WhatsApp, pays via bank transfer, and you get notified instantly
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* 4 Features Showcase */}
      <section className="px-4 py-20 sm:px-6 lg:px-8 bg-gradient-to-b from-white to-slate-50">
        <div className="mx-auto max-w-7xl">
          <div className="text-center">
            <h2 className="text-base font-semibold text-blue-600">POWERFUL FEATURES</h2>
            <p className="mt-2 text-4xl font-bold text-slate-900 sm:text-5xl">
              4 Ways to Create Invoices
            </p>
            <p className="mt-4 text-lg text-slate-600 max-w-2xl mx-auto">
              Choose the method that works best for you. All powered by AI, all in seconds.
            </p>
          </div>

          <div className="mt-16 grid gap-8 lg:grid-cols-2">
            {/* Feature 1: WhatsApp Text */}
            <div className="group relative overflow-hidden rounded-3xl border-2 border-slate-200 bg-white p-8 shadow-lg hover:shadow-2xl hover:border-blue-400 transition-all duration-300">
              <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-blue-500/10 to-purple-500/10 rounded-full blur-3xl"></div>
              <div className="relative">
                <div className="flex items-start justify-between">
                  <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-blue-600 text-3xl shadow-lg">
                    💬
                  </div>
                  <span className="rounded-full bg-green-100 px-3 py-1 text-xs font-semibold text-green-700">
                    ⚡ 5 seconds
                  </span>
                </div>
                <h3 className="mt-6 text-2xl font-bold text-slate-900">WhatsApp Text</h3>
                <p className="mt-2 text-slate-600">
                  Type and send. No forms, no calculations, just simple text.
                </p>
                
                <div className="mt-6 rounded-xl bg-slate-50 p-4 border border-slate-200">
                  <p className="text-sm font-mono text-slate-700">
                    &quot;Invoice Jane 50k for logo&quot;
                  </p>
                  <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
                    <span className="flex items-center gap-1">
                      <svg className="h-4 w-4 text-green-500" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                      Invoice created
                    </span>
                    <span>→</span>
                    <span>5 sec</span>
                  </div>
                </div>

                <ul className="mt-6 space-y-3">
                  <li className="flex items-start gap-3 text-sm text-slate-600">
                    <svg className="h-5 w-5 text-blue-500 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span><strong>Perfect for:</strong> When you&apos;re at your desk or prefer typing</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm text-slate-600">
                    <svg className="h-5 w-5 text-blue-500 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>AI understands Nigerian English and currency</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm text-slate-600">
                    <svg className="h-5 w-5 text-blue-500 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>Works offline - sends when you&apos;re back online</span>
                  </li>
                </ul>
              </div>
            </div>

            {/* Feature 2: Voice Notes */}
            <div className="group relative overflow-hidden rounded-3xl border-2 border-slate-200 bg-white p-8 shadow-lg hover:shadow-2xl hover:border-purple-400 transition-all duration-300">
              <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-purple-500/10 to-pink-500/10 rounded-full blur-3xl"></div>
              <div className="relative">
                <div className="flex items-start justify-between">
                  <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-purple-500 to-purple-600 text-3xl shadow-lg">
                    🎤
                  </div>
                  <span className="rounded-full bg-green-100 px-3 py-1 text-xs font-semibold text-green-700">
                    ⚡ 10 seconds
                  </span>
                </div>
                <h3 className="mt-6 text-2xl font-bold text-slate-900">Voice Notes</h3>
                <p className="mt-2 text-slate-600">
                  Speak naturally. AI transcribes and creates invoice instantly.
                </p>
                
                <div className="mt-6 rounded-xl bg-slate-50 p-4 border border-slate-200">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-purple-500 text-white">
                      <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clipRule="evenodd" />
                      </svg>
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium text-slate-700">0:15 audio</p>
                      <p className="text-xs text-slate-500 italic">
                        &quot;Invoice Jane fifty thousand for logo&quot;
                      </p>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
                    <span className="flex items-center gap-1">
                      <svg className="h-4 w-4 text-green-500" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                      Transcribed + Invoice created
                    </span>
                    <span>→</span>
                    <span>10 sec</span>
                  </div>
                </div>

                <ul className="mt-6 space-y-3">
                  <li className="flex items-start gap-3 text-sm text-slate-600">
                    <svg className="h-5 w-5 text-purple-500 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span><strong>Perfect for:</strong> When you&apos;re driving, busy, or prefer talking</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm text-slate-600">
                    <svg className="h-5 w-5 text-purple-500 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>Truly hands-free - no typing required</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm text-slate-600">
                    <svg className="h-5 w-5 text-purple-500 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>AI-powered transcription with Nigerian English support</span>
                  </li>
                </ul>
              </div>
            </div>

            {/* Feature 3: Photo OCR */}
            <div className="group relative overflow-hidden rounded-3xl border-2 border-slate-200 bg-white p-8 shadow-lg hover:shadow-2xl hover:border-orange-400 transition-all duration-300">
              <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-orange-500/10 to-yellow-500/10 rounded-full blur-3xl"></div>
              <div className="relative">
                <div className="flex items-start justify-between">
                  <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-orange-500 to-orange-600 text-3xl shadow-lg">
                    📸
                  </div>
                  <span className="rounded-full bg-green-100 px-3 py-1 text-xs font-semibold text-green-700">
                    ⚡ 8 seconds
                  </span>
                </div>
                <h3 className="mt-6 text-2xl font-bold text-slate-900">Photo OCR</h3>
                <p className="mt-2 text-slate-600">
                  Snap a receipt photo. AI reads it and creates your invoice.
                </p>
                
                <div className="mt-6 rounded-xl bg-slate-50 p-4 border border-slate-200">
                  <div className="flex items-center gap-3">
                    <div className="relative w-16 h-16 rounded-lg bg-slate-200 flex items-center justify-center text-2xl overflow-hidden">
                      📄
                      <div className="absolute inset-0 border-2 border-dashed border-slate-400 rounded-lg"></div>
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium text-slate-700">Receipt uploaded</p>
                      <p className="text-xs text-slate-500">AI extracting data...</p>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
                    <span className="flex items-center gap-1">
                      <svg className="h-4 w-4 text-green-500" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                      </svg>
                      Data extracted + Invoice created
                    </span>
                    <span>→</span>
                    <span>8 sec</span>
                  </div>
                </div>

                <ul className="mt-6 space-y-3">
                  <li className="flex items-start gap-3 text-sm text-slate-600">
                    <svg className="h-5 w-5 text-orange-500 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span><strong>Perfect for:</strong> Converting handwritten receipts to digital invoices</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm text-slate-600">
                    <svg className="h-5 w-5 text-orange-500 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>No retyping - AI reads customer name, amount, items</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm text-slate-600">
                    <svg className="h-5 w-5 text-orange-500 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>Available on Starter plan and above</span>
                  </li>
                </ul>
              </div>
            </div>

            {/* Feature 4: QR Verification */}
            <div className="group relative overflow-hidden rounded-3xl border-2 border-slate-200 bg-white p-8 shadow-lg hover:shadow-2xl hover:border-green-400 transition-all duration-300">
              <div className="absolute top-0 right-0 w-32 h-32 bg-gradient-to-br from-green-500/10 to-emerald-500/10 rounded-full blur-3xl"></div>
              <div className="relative">
                <div className="flex items-start justify-between">
                  <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-green-500 to-green-600 text-3xl shadow-lg">
                    🔐
                  </div>
                  <span className="rounded-full bg-green-100 px-3 py-1 text-xs font-semibold text-green-700">
                    ⚡ 2 seconds
                  </span>
                </div>
                <h3 className="mt-6 text-2xl font-bold text-slate-900">QR Verification</h3>
                <p className="mt-2 text-slate-600">
                  Every invoice includes a QR code. Customers scan it to verify authenticity instantly.
                </p>
                
                <div className="mt-6 rounded-xl bg-slate-50 p-4 border border-slate-200">
                  <div className="flex items-center gap-3">
                    <div className="w-16 h-16 bg-slate-900 rounded-lg flex items-center justify-center">
                      <div className="grid grid-cols-4 gap-0.5">
                        {[...Array(16)].map((_, i) => (
                          <div key={i} className="w-1.5 h-1.5 bg-white rounded-sm"></div>
                        ))}
                      </div>
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-medium text-slate-700">Customer scanning QR...</p>
                      <p className="text-xs text-slate-500">Verifying invoice...</p>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <div className="flex-1 rounded-lg bg-green-100 px-3 py-2 text-center">
                      <p className="text-lg font-bold text-green-700">✅ VERIFIED</p>
                      <p className="text-xs text-green-600">Invoice is authentic</p>
                    </div>
                  </div>
                </div>

                <ul className="mt-6 space-y-3">
                  <li className="flex items-start gap-3 text-sm text-slate-600">
                    <svg className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span><strong>Perfect for:</strong> Building customer trust - prove invoices are legitimate</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm text-slate-600">
                    <svg className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>Stop impersonation - only your real invoices have valid QR codes</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm text-slate-600">
                    <svg className="h-5 w-5 text-green-500 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                      <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                    </svg>
                    <span>Works with any phone camera - no special app needed</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>

          {/* Before/After Comparison */}
          <div className="mt-20 rounded-3xl bg-gradient-to-r from-slate-900 to-slate-800 p-8 lg:p-12 shadow-2xl">
            <h3 className="text-center text-3xl font-bold text-white sm:text-4xl">
              The Problem We Solve
            </h3>
            <div className="mt-12 grid gap-8 lg:grid-cols-2">
              {/* Before */}
              <div className="rounded-2xl bg-red-900/30 border-2 border-red-500/50 p-6">
                <div className="flex items-center gap-3 mb-4">
                  <span className="text-3xl">😓</span>
                  <h4 className="text-xl font-bold text-red-200">Without SuoOps</h4>
                </div>
                <ul className="space-y-3 text-slate-300">
                  <li className="flex items-start gap-3">
                    <span className="text-red-400 mt-1">✗</span>
                    <span>Spend 10+ minutes creating each invoice manually</span>
                  </li>
                  <li className="flex items-start gap-3">
                    <span className="text-red-400 mt-1">✗</span>
                    <span>Customers can&apos;t verify if invoices are legitimate</span>
                  </li>
                  <li className="flex items-start gap-3">
                    <span className="text-red-400 mt-1">✗</span>
                    <span>Risk of fake invoices impersonating your business</span>
                  </li>
                  <li className="flex items-start gap-3">
                    <span className="text-red-400 mt-1">✗</span>
                    <span>Manually retype receipt details (slow & error-prone)</span>
                  </li>
                  <li className="flex items-start gap-3">
                    <span className="text-red-400 mt-1">✗</span>
                    <span>Need computer access to create invoices</span>
                  </li>
                </ul>
              </div>

              {/* After */}
              <div className="rounded-2xl bg-green-900/30 border-2 border-green-500/50 p-6">
                <div className="flex items-center gap-3 mb-4">
                  <span className="text-3xl">🚀</span>
                  <h4 className="text-xl font-bold text-green-200">With SuoOps</h4>
                </div>
                <ul className="space-y-3 text-slate-300">
                  <li className="flex items-start gap-3">
                    <span className="text-green-400 mt-1">✓</span>
                    <span>Create invoices in 5-10 seconds via WhatsApp</span>
                  </li>
                  <li className="flex items-start gap-3">
                    <span className="text-green-400 mt-1">✓</span>
                    <span>Every invoice has a QR code for authenticity verification</span>
                  </li>
                  <li className="flex items-start gap-3">
                    <span className="text-green-400 mt-1">✓</span>
                    <span>Build trust - customers can verify invoices are legitimate</span>
                  </li>
                  <li className="flex items-start gap-3">
                    <span className="text-green-400 mt-1">✓</span>
                    <span>Snap receipt photos - AI extracts all details automatically</span>
                  </li>
                  <li className="flex items-start gap-3">
                    <span className="text-green-400 mt-1">✓</span>
                    <span>Work from anywhere - just use your phone</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>

          {/* Quick Stats */}
          <div className="mt-16 grid gap-6 sm:grid-cols-4">
            <div className="text-center rounded-2xl bg-blue-50 border border-blue-200 p-6">
              <div className="text-4xl font-bold text-blue-600">5s</div>
              <div className="mt-2 text-sm font-medium text-slate-600">Text Invoice</div>
            </div>
            <div className="text-center rounded-2xl bg-purple-50 border border-purple-200 p-6">
              <div className="text-4xl font-bold text-purple-600">10s</div>
              <div className="mt-2 text-sm font-medium text-slate-600">Voice Invoice</div>
            </div>
            <div className="text-center rounded-2xl bg-orange-50 border border-orange-200 p-6">
              <div className="text-4xl font-bold text-orange-600">8s</div>
              <div className="mt-2 text-sm font-medium text-slate-600">Photo OCR</div>
            </div>
            <div className="text-center rounded-2xl bg-green-50 border border-green-200 p-6">
              <div className="text-4xl font-bold text-green-600">2s</div>
              <div className="mt-2 text-sm font-medium text-slate-600">QR Verify</div>
            </div>
          </div>
        </div>
      </section>

      {/* Pricing Preview */}
      <section id="pricing" className="bg-slate-50 px-4 py-20 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-7xl text-center">
          <h2 className="text-base font-semibold text-blue-600">PRICING</h2>
          <p className="mt-2 text-4xl font-bold text-slate-900">
            Start free, upgrade as you grow
          </p>
          <div className="mt-12 grid gap-6 sm:grid-cols-2 lg:grid-cols-5">
            {[
              { 
                name: "Free", 
                price: "₦0", 
                invoices: "5/month",
                features: ["Manual invoices only", "WhatsApp bot", "PDF generation", "Email notifications"]
              },
              { 
                name: "Starter", 
                price: "₦2,500", 
                invoices: "100/month", 
                popular: false,
                features: ["All Free features", "Photo invoice OCR", "Voice invoices", "Custom branding"]
              },
              { 
                name: "Pro", 
                price: "₦7,500", 
                invoices: "1,000/month", 
                popular: true,
                features: ["All Starter features", "Priority support", "Advanced analytics", "API access"]
              },
              { 
                name: "Business", 
                price: "₦15,000", 
                invoices: "3,000/month",
                features: ["All Pro features", "Dedicated support", "Custom integrations", "Team management"]
              },
              { 
                name: "Enterprise", 
                price: "₦50,000", 
                invoices: "Unlimited",
                features: ["All Business features", "White-label option", "SLA guarantee", "Custom contracts"]
              },
            ].map((plan, i) => (
              <div
                key={i}
                className={`rounded-2xl border bg-white p-6 ${
                  plan.popular ? "border-blue-500 ring-2 ring-blue-500" : "border-slate-200"
                }`}
              >
                {plan.popular && (
                  <div className="mb-2 text-xs font-semibold text-blue-600">MOST POPULAR</div>
                )}
                <h3 className="text-lg font-bold text-slate-900">{plan.name}</h3>
                <div className="mt-2">
                  <span className="text-3xl font-bold">{plan.price}</span>
                  <span className="text-slate-600">/mo</span>
                </div>
                <p className="mt-2 text-sm font-semibold text-slate-900">{plan.invoices}</p>
                <ul className="mt-4 space-y-2 text-left text-xs text-slate-600">
                  {plan.features.map((feature, j) => (
                    <li key={j} className="flex items-start gap-2">
                      <span className="text-green-600">✓</span>
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <a
            href="https://docs.google.com/forms/d/e/1FAIpQLSc8s7K5WNC_6xDzg2IlUMJtxzvF4T18YwYlW_ruHMyC6IT5yg/viewform"
            target="_blank"
            rel="noopener noreferrer"
            className="mt-8 inline-block rounded-lg bg-blue-600 px-8 py-4 font-semibold text-white hover:bg-blue-700 transition-colors"
          >
            Join Waitlist →
          </a>
        </div>
      </section>

      {/* CTA Section */}
      <section className="relative overflow-hidden bg-gradient-to-br from-blue-600 to-purple-600 px-4 py-20 sm:px-6 lg:px-8">
        <div className="relative mx-auto max-w-4xl text-center">
          <h2 className="text-4xl font-bold text-white sm:text-5xl">
            Be the first to experience it
          </h2>
          <p className="mt-4 text-xl text-blue-100">
            Join our waitlist and get exclusive early access when we launch!
          </p>
          <div className="mt-8 flex flex-col gap-4 sm:flex-row sm:justify-center">
            <a
              href="https://docs.google.com/forms/d/e/1FAIpQLSc8s7K5WNC_6xDzg2IlUMJtxzvF4T18YwYlW_ruHMyC6IT5yg/viewform"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-white px-8 py-4 text-center text-base font-semibold text-blue-600 shadow-lg hover:bg-blue-50 transition-all hover:scale-105"
            >
              🚀 Join Waitlist Now
            </a>
          </div>
          <p className="mt-6 text-sm text-blue-100">
            ✓ 50% launch discount · ✓ Priority early access · ✓ Exclusive updates
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-200 bg-white px-4 py-12 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-7xl">
          <div className="grid gap-8 md:grid-cols-4">
            <div>
              <div className="flex items-center gap-2">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-blue-700 text-2xl font-bold text-white">
                  S
                </div>
                <span className="text-xl font-bold text-slate-900">SuoOps</span>
              </div>
              <p className="mt-4 text-sm text-slate-600">
                The easiest way for Nigerian businesses to create invoices and get paid.
              </p>
            </div>
            <div>
              <h3 className="font-semibold text-slate-900">Product</h3>
              <ul className="mt-4 space-y-2 text-sm text-slate-600">
                <li><a href="#features" className="hover:text-slate-900">Features</a></li>
                <li><a href="#pricing" className="hover:text-slate-900">Pricing</a></li>
                <li><Link href="/dashboard" className="hover:text-slate-900">Dashboard</Link></li>
              </ul>
            </div>
            <div>
              <h3 className="font-semibold text-slate-900">Company</h3>
              <ul className="mt-4 space-y-2 text-sm text-slate-600">
                <li><a href="mailto:info@suoops.com" className="hover:text-slate-900">Contact</a></li>
                <li><a href="https://api.suoops.com/healthz" target="_blank" rel="noopener noreferrer" className="hover:text-slate-900">Status</a></li>
                <li><Link href="/login" className="hover:text-slate-900">Login</Link></li>
              </ul>
            </div>
            <div>
              <h3 className="font-semibold text-slate-900">Legal</h3>
              <ul className="mt-4 space-y-2 text-sm text-slate-600">
                <li><Link href="/privacy" className="hover:text-slate-900">Privacy Policy</Link></li>
                <li><Link href="/terms" className="hover:text-slate-900">Terms of Service</Link></li>
              </ul>
            </div>
          </div>
          <div className="mt-12 border-t border-slate-200 pt-8 text-center text-sm text-slate-500">
            © 2025 SuoOps. All rights reserved. Made with ❤️ in Nigeria 🇳🇬
          </div>
        </div>
      </footer>

      {/* Video Modal */}
      {showVideoModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"
          onClick={() => setShowVideoModal(false)}
        >
          <div
            className="relative w-full max-w-4xl"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              onClick={() => setShowVideoModal(false)}
              className="absolute -top-12 right-0 text-white hover:text-slate-300 text-4xl font-light"
              aria-label="Close video"
            >
              ×
            </button>
            <div className="relative aspect-video w-full overflow-hidden rounded-lg bg-black shadow-2xl">
              <iframe
                src="https://www.youtube.com/embed/l5VocoSn7yc?autoplay=1"
                title="SuoOps Demo"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                className="h-full w-full"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
