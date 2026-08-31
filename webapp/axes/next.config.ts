import type { NextConfig } from "next";

const integrationsApiUrl = (process.env.INTEGRATIONS_API_URL ?? "").replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    if (!integrationsApiUrl) {
      return [];
    }
    return [
      {
        source: "/app_integrations/github/:path*",
        destination: `${integrationsApiUrl}/app_integrations/github/:path*`,
      },
    ];
  },
};

export default nextConfig;
