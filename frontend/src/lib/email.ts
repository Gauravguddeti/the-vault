import nodemailer from "nodemailer";

const transporter = nodemailer.createTransport({
  service: "gmail",
  auth: {
    user: process.env.EMAIL_FROM,
    pass: process.env.EMAIL_APP_PASSWORD,
  },
});

export async function sendOtpEmail(to: string, otp: string): Promise<void> {
  await transporter.sendMail({
    from: `"The Vault" <${process.env.EMAIL_FROM}>`,
    to,
    subject: "Your Vault Password Reset Code",
    html: `
      <div style="font-family:Inter,sans-serif;max-width:480px;margin:0 auto;background:#0f0f1a;color:#f1f5f9;padding:40px;border-radius:16px;border:1px solid rgba(99,102,241,0.2)">
        <div style="text-align:center;margin-bottom:32px">
          <div style="display:inline-flex;align-items:center;justify-content:center;width:56px;height:56px;background:linear-gradient(135deg,#4f46e5,#7c3aed);border-radius:14px;margin-bottom:16px">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          </div>
          <h1 style="margin:0;font-size:22px;font-weight:700;background:linear-gradient(135deg,#818cf8,#c084fc);-webkit-background-clip:text;-webkit-text-fill-color:transparent">The Vault</h1>
        </div>
        <h2 style="font-size:18px;font-weight:600;margin:0 0 8px;color:#f1f5f9">Password Reset</h2>
        <p style="color:#94a3b8;margin:0 0 24px;line-height:1.6">Use the code below to reset your password. This code expires in <strong style="color:#f1f5f9">15 minutes</strong>.</p>
        <div style="background:rgba(99,102,241,0.12);border:1px solid rgba(99,102,241,0.3);border-radius:12px;padding:24px;text-align:center;margin-bottom:24px">
          <span style="font-size:40px;font-weight:800;letter-spacing:12px;color:#818cf8;font-family:monospace">${otp}</span>
        </div>
        <p style="color:#64748b;font-size:13px;margin:0">If you didn't request this, you can safely ignore this email. Your password won't be changed.</p>
      </div>
    `,
  });
}
