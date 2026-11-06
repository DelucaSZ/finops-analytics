import messages from "./messages/pt-BR.json";

declare module "next-intl" {
  interface AppConfig {
    Locale: "pt-BR" | "en-US";
    Messages: typeof messages;
  }
}
