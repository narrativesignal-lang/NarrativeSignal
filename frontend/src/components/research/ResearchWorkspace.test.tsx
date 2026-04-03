import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ResearchWorkspace } from "./ResearchWorkspace";

vi.mock("@/lib/i18n", () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, string | number>) => {
      const map: Record<string, string> = {
        "research.addBlock": "+ Add Block",
        "workspace.addBlock": "Add Block",
        "workspace.overlayChart": "Overlay Chart",
        "workspace.splitChart": "Split Chart",
        "workspace.analysis": "Analysis",
        "common.cancel": "Cancel",
        "common.add": "Add",
        "workspace.sameTimelineNote": "Only same-timeline compatible series can be added here.",
        "workspace.overlayTabHint": "Overlay hint text.",
        "workspace.overlaySelectedCount": "{count} selected",
        "workspace.modalNoOverlayOptions": "No overlay options",
        "workspace.modalNoSplitOptions": "No split options",
        "workspace.modalNoAnalysisOptions": "No analysis options",
        "workspace.noResearchTarget": "No research target configured for this tab.",
        "research.addBlockNeedSetupTitle": "Configure universe first",
        "research.maxBlocksTabLine": "Max blocks reached",
        "research.blocksCount": "Blocks",
        "schedules.comingUp": "Coming up",
        "schedules.premiumPlanned": "Premium planned",
      };
      let s = map[key] ?? key;
      if (params) {
        for (const [k, v] of Object.entries(params)) {
          s = s.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
        }
      }
      return s;
    },
  }),
}));

vi.mock("@/lib/UserContext", () => ({
  useUser: () => ({
    user: {
      id: "u1",
      username: "t",
      email: "t@t",
      profile_name: "",
      credits_balance: 100,
      paid_access: false,
      is_admin: false,
    },
    loading: false,
    refetch: async () => {},
  }),
}));

function openAddBlockModal() {
  const addButtons = screen.getAllByRole("button", { name: /add block/i });
  fireEvent.click(addButtons[0]);
  return screen.getByRole("dialog", { name: /add block/i });
}

const defaultTab = {
  id: "tab-1",
  title: "Default",
  setup: { terms: ["test"] } as Record<string, unknown>,
  panels: [] as Array<{ type: string; kind?: string }>,
};

const mockProject = {
  id: "proj-1",
  folder_id: "folder-1",
  name: "Test Project",
  layout_type: "single",
  layout_config: { tabs: [defaultTab], active_tab_id: "tab-1" },
  created_at: "2024-01-01T00:00:00Z",
};

vi.mock("@/lib/api", () => ({
  api: {
    updateResearchProject: vi.fn((id: string, payload: { layout_config?: Record<string, unknown> }) =>
      Promise.resolve({
        ...mockProject,
        layout_config: payload?.layout_config ?? mockProject.layout_config,
      })
    ),
    listPortfolios: vi.fn(() => Promise.resolve([])),
    listGroups: vi.fn(() => Promise.resolve([])),
    listEntities: vi.fn(() => Promise.resolve([])),
    getEntity: vi.fn(() => Promise.resolve({ id: "e1", name: "Entity", terms: [], instrument: null, portfolio_id: "p1", portfolio_name: "P", instrument_id: null, created_at: "", updated_at: "" })),
    searchInstruments: vi.fn(() => Promise.resolve([])),
    listResearchSetupSnapshots: vi.fn(() => Promise.resolve([])),
    saveResearchSetupSnapshot: vi.fn(() => Promise.resolve({ code: "RS-ABC123" })),
    importResearchSetupSnapshot: vi.fn(() => Promise.resolve({ config: { tab_title: "Imported", setup: {}, panels: [] } })),
    updateResearchSetupSnapshot: vi.fn(() => Promise.resolve({ code: "RS-X", name: null, created_at: "" })),
    deleteResearchSetupSnapshot: vi.fn(() => Promise.resolve()),
  },
}));

describe("ResearchWorkspace Add Block flow (modal)", () => {
  it("opens Add Block modal when '+ Add Block' is clicked", () => {
    const onUpdate = vi.fn();
    render(<ResearchWorkspace project={mockProject} onUpdate={onUpdate} />);

    expect(screen.getAllByRole("button", { name: /add block/i })[0]).toBeInTheDocument();

    const dialog = openAddBlockModal();
    expect(dialog).toBeInTheDocument();
    expect(within(dialog).getByText("Add Block")).toBeInTheDocument();
    expect(screen.getByText("Overlay Chart")).toBeInTheDocument();
    expect(screen.getByText("Split Chart")).toBeInTheDocument();
    expect(screen.getByText("Analysis")).toBeInTheDocument();
  });

  it("adds block via modal: category then block then Add", async () => {
    const onUpdate = vi.fn();
    const { api } = await import("@/lib/api");
    const updateMock = vi.mocked(api.updateResearchProject);

    render(<ResearchWorkspace project={mockProject} onUpdate={onUpdate} />);
    const dialog = openAddBlockModal();

    fireEvent.click(within(dialog).getByRole("button", { name: /split chart/i }));
    fireEvent.click(within(dialog).getByRole("button", { name: /^sentiment$/i }));
    fireEvent.click(within(dialog).getByRole("button", { name: /^add$/i }));

    expect(updateMock).toHaveBeenCalledWith(
      "proj-1",
      expect.objectContaining({
        layout_config: expect.objectContaining({
          tabs: expect.any(Array),
          active_tab_id: "tab-1",
        }),
      })
    );
    const lastCall = updateMock.mock.calls[updateMock.mock.calls.length - 1];
    const sent = lastCall[1].layout_config as { tabs: Array<{ panels: Array<{ type: string; kind?: string }> }> };
    expect(sent.tabs[0].panels).toHaveLength(1);
    expect(sent.tabs[0].panels[0].type).toBe("sentiment");
    expect(sent.tabs[0].panels[0].kind).toBe("single");
  });

  it("3D blocks only under Analysis category and can be added", async () => {
    const onUpdate = vi.fn();
    const { api } = await import("@/lib/api");
    const updateMock = vi.mocked(api.updateResearchProject);

    render(<ResearchWorkspace project={mockProject} onUpdate={onUpdate} />);
    const dialog = openAddBlockModal();

    fireEvent.click(within(dialog).getByRole("button", { name: /^analysis$/i }));
    expect(within(dialog).getByRole("button", { name: /3d narrative space/i })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: /3d derivative space/i })).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole("button", { name: /3d narrative space/i }));
    fireEvent.click(within(dialog).getByRole("button", { name: /^add$/i }));

    expect(updateMock).toHaveBeenCalledWith(
      "proj-1",
      expect.objectContaining({
        layout_config: expect.objectContaining({
          tabs: expect.any(Array),
          active_tab_id: "tab-1",
        }),
      })
    );
    const lastCall = updateMock.mock.calls[updateMock.mock.calls.length - 1];
    const sent = lastCall[1].layout_config as { tabs: Array<{ panels: Array<{ type: string; kind?: string }> }> };
    expect(sent.tabs[0].panels).toHaveLength(1);
    expect(sent.tabs[0].panels[0].type).toBe("three_d_narrative");
    expect(sent.tabs[0].panels[0].kind).toBe("analysis");
  });

  it("Overlay Chart shows same-timeline note", () => {
    render(<ResearchWorkspace project={mockProject} onUpdate={vi.fn()} />);
    const dialog = openAddBlockModal();
    fireEvent.click(within(dialog).getByRole("button", { name: /overlay chart/i }));

    expect(
      within(dialog).getByText(/only same-timeline compatible series can be added here/i)
    ).toBeInTheDocument();
  });

  it("shows incomplete state when no research target configured", () => {
    const projectNoTarget = {
      id: "proj-1",
      folder_id: "folder-1",
      name: "Test Project",
      layout_type: "single",
      layout_config: {
        tabs: [{ id: "tab-1", title: "Default", setup: {}, panels: [] }],
        active_tab_id: "tab-1",
      },
      created_at: "2024-01-01T00:00:00Z",
    };
    render(<ResearchWorkspace project={projectNoTarget} onUpdate={vi.fn()} />);
    const dialog = openAddBlockModal();
    const addBtn = within(dialog).getByRole("button", { name: /^add$/i });
    expect(addBtn).toBeDisabled();
  });
});
