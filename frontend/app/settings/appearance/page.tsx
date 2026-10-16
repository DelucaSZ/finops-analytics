import { PageHeader } from "@/components/page-header";
import { ThemeSelector } from "@/components/theme-selector";

export default function AppearanceSettingsPage() {
  return (
    <>
      <PageHeader
        eyebrow="PREFERÊNCIAS"
        title="Aparência"
        description="Ajuste o tema visual do DeepOps neste navegador."
      />
      <section className="panel settings-preference-panel" aria-labelledby="appearance-heading">
        <div className="panel-heading settings-preference-heading">
          <div>
            <h2 id="appearance-heading">Tema da interface</h2>
            <p>Novos usuários usam a preferência do sistema por padrão.</p>
          </div>
        </div>
        <div className="settings-preference-body">
          <ThemeSelector />
        </div>
      </section>
    </>
  );
}
