import express from "express";
import crypto from "node:crypto";
import { controlChannelRouter } from "./controlChannel.js";
import {
  indexPage,
  fixtureA,
  fixtureB,
  fixtureC,
  fixtureD,
  fixtureE,
  fixtureEChild,
  fixtureF,
  fixtureFInner,
  fixtureG,
  fixtureH,
  fixtureI,
  fixtureIDashboard,
  fixtureIDashboardPopup,
  fixtureJ,
  fixtureL,
} from "./pages.js";

export function buildApp() {
  const app = express();
  app.use(express.json());
  app.use(controlChannelRouter());

  app.get("/", (_req, res) => res.type("html").send(indexPage()));

  app.get("/fixtures/a", (_req, res) => res.type("html").send(fixtureA()));
  app.get("/fixtures/b", (_req, res) => res.type("html").send(fixtureB()));
  app.get("/fixtures/c", (_req, res) => res.type("html").send(fixtureC()));
  app.get("/fixtures/d", (_req, res) => res.type("html").send(fixtureD()));

  app.get("/fixtures/e", (_req, res) => res.type("html").send(fixtureE()));
  app.get("/fixtures/e/child", (_req, res) => res.type("html").send(fixtureEChild()));

  app.get("/fixtures/f", (_req, res) => res.type("html").send(fixtureF()));
  app.get("/fixtures/f/inner", (req, res) => {
    const label = String(req.query.label ?? "?");
    const nested = req.query.nested === "1";
    res.type("html").send(fixtureFInner(label, nested));
  });

  app.get("/fixtures/g", (_req, res) => res.type("html").send(fixtureG()));

  app.get("/fixtures/h", (req, res) => res.type("html").send(fixtureH(req.query.seed === "1")));

  app.get("/fixtures/i", (_req, res) => res.type("html").send(fixtureI()));
  app.get("/fixtures/i/dashboard", (_req, res) => res.type("html").send(fixtureIDashboard()));
  app.get("/fixtures/i/dashboard-popup", (_req, res) => res.type("html").send(fixtureIDashboardPopup()));

  app.get("/fixtures/j", (_req, res) => res.type("html").send(fixtureJ()));
  app.get("/fixtures/j/file", (req, res) => {
    const name = String(req.query.name ?? "file.bin");
    const size = Math.max(1, Number(req.query.size ?? 1024));
    const delayMs = Number(req.query.delayMs ?? 0);
    const send = () => {
      const buf = crypto.createHash("sha256").update(name).digest();
      const content = Buffer.alloc(size);
      for (let i = 0; i < size; i++) content[i] = buf[i % buf.length];
      res.setHeader("Content-Disposition", `attachment; filename="${name}"`);
      res.setHeader("Content-Type", "application/octet-stream");
      res.setHeader("Content-Length", String(size));
      res.send(content);
    };
    if (delayMs > 0) setTimeout(send, delayMs);
    else send();
  });
  app.get("/fixtures/j/fail", (req, res) => {
    const name = String(req.query.name ?? "broken.bin");
    res.setHeader("Content-Disposition", `attachment; filename="${name}"`);
    res.setHeader("Content-Type", "application/octet-stream");
    // Announce more bytes than we actually send, then hard-kill the socket
    // so the browser observes a genuinely failed/incomplete download rather
    // than a server-side 500 (which some UAs would just render as text).
    res.setHeader("Content-Length", "1000000");
    res.status(200);
    res.write(Buffer.alloc(1024, 1));
    setTimeout(() => {
      res.destroy();
    }, 50);
  });

  app.get("/fixtures/l", (_req, res) => res.type("html").send(fixtureL()));

  return app;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const port = Number(process.env.FIXTURE_PORT ?? 4173);
  const app = buildApp();
  app.listen(port, () => {
    console.log(`fixture server listening on http://localhost:${port}`);
  });
}
