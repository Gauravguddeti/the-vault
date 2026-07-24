import { NextRequest, NextResponse } from "next/server";
import { Pool } from "pg";
import crypto from "crypto";
import { sendOtpEmail } from "@/lib/email";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

function generateOtp(): string {
  return crypto.randomInt(100000, 999999).toString();
}

function hashOtp(otp: string): string {
  return crypto.createHash("sha256").update(otp).digest("hex");
}

export async function POST(req: NextRequest) {
  try {
    const { email } = await req.json();
    if (!email) return NextResponse.json({ error: "Email is required" }, { status: 400 });

    // Check user exists
    const result = await pool.query("SELECT id FROM users WHERE email = $1", [email.toLowerCase()]);
    if (result.rows.length === 0) {
      // Don't reveal if user exists — return success anyway for security
      return NextResponse.json({ message: "If that email exists, a code was sent." });
    }

    // Invalidate old tokens for this email
    await pool.query("UPDATE password_reset_tokens SET used=true WHERE email=$1 AND used=false", [email.toLowerCase()]);

    const otp = generateOtp();
    const otpHash = hashOtp(otp);
    const expiresAt = new Date(Date.now() + 15 * 60 * 1000); // 15 min

    await pool.query(
      "INSERT INTO password_reset_tokens (email, otp_hash, expires_at) VALUES ($1, $2, $3)",
      [email.toLowerCase(), otpHash, expiresAt]
    );

    await sendOtpEmail(email.toLowerCase(), otp);

    return NextResponse.json({ message: "If that email exists, a code was sent." });
  } catch (err) {
    console.error("Forgot password error:", err);
    return NextResponse.json({ error: "Failed to send reset code." }, { status: 500 });
  }
}
