import { PageHeader, Section } from "@/components/aven";
import { ThemeSelector } from "@/components/theme-selector";
import { PRODUCT_NAME } from "@/lib/brand";

export default function AppearanceSettingsPage() {
  return (
    <>
      <PageHeader
        title="Aparência"
        description={`Ajuste o tema visual do ${PRODUCT_NAME} neste navegador.`}
      />
      <Section
        appearance="card"
        title="Tema da interface"
        description="Novos usuários usam a preferência do sistema por padrão."
      >
        <ThemeSelector />
      </Section>
    </>
  );
}
