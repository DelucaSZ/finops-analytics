import { getTranslations } from "next-intl/server";
import { PageHeader, Section } from "@/components/aven";
import { ThemeSelector } from "@/components/theme-selector";
import { PRODUCT_NAME } from "@/lib/brand";

export default async function AppearanceSettingsPage() {
  const t = await getTranslations("settings.appearance");
  return (
    <>
      <PageHeader
        title={t("title")}
        description={t("description", {product: PRODUCT_NAME})}
      />
      <Section
        appearance="card"
        title={t("themeTitle")}
        description={t("themeDescription")}
      >
        <ThemeSelector />
      </Section>
    </>
  );
}
