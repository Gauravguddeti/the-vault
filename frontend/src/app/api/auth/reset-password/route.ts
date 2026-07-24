import { NextRequest, NextResponse } from "next/server";
import { Pool } from "pg";
import crypto from "crypto";
import bcrypt from "bcryptjs";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

function hashOtp(otp: string): string {
  return crypto.createHash("sha256").update(otp).digest("hex");
}

export async function POST(req: NextRequest) {
  try {
    const { email, otp, newPassword } = await req.json();

    if (!email || !otp || !newPassword)
      return NextResponse.json({ error: "Email, OTP, and new password are required" }, { status: 400 });

    if (newPassword.length < 8)
      return NextResponse.json({ error: "Password must be at least 8 characters" }, { status: 400 });

    const otpHash = hashOtp(otp.trim());

    // Verify OTP
    const tokenResult = await pool.query(
      `SELECT id FROM password_reset_tokens
       WHERE email=$1 AND otp_hash=$2 AND used=false AND expires_at > NOW()`,
      [email.toLowerCase(), otpHash]
    );

    if (tokenResult.rows.length === 0) {
      return NextResponse.json({ error: "Invalid or expired code. Please request a new one." }, { status: 400 });
    }

    // Mark token as used
    await pool.query(
      "UPDATE password_reset_tokens SET used=true WHERE id=$1",
      [tokenResult.rows[0].id]
    );

    // Update password
    const passwordHash = await bcrypt.hash(newPassword, 12);
    await pool.query(
      "UPDATE users SET password_hash=$1, updated_at=NOW() WHERE email=$2",
      [passwordHash, email.toLowerCase()]
    );

    return NextResponse.json({ message: "Password updated successfully." });
  } catch (err) {
    console.error("Reset password error:", err);
    return NextResponse.json({ error: "Failed to reset password." }, { status: 500 });
  }
}
