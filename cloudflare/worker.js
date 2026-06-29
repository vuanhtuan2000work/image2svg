import { Container, getContainer } from "@cloudflare/containers";

const CONVERT_PATHS = new Set([
  "/",
  "/api/meta",
  "/api/convert",
  "/api/export-zip",
  "/favicon.ico",
]);

function isConvertScreenPath(pathname) {
  return CONVERT_PATHS.has(pathname) || pathname.startsWith("/static/");
}

export class Image2SvgContainer extends Container {
  defaultPort = 8080;
  sleepAfter = "10m";
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!isConvertScreenPath(url.pathname)) {
      return new Response("Not found", { status: 404 });
    }

    const container = getContainer(env.IMAGE2SVG_CONTAINER, "convert");
    return container.fetch(request);
  },
};
