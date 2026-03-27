import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Shell } from "./Shell";

const mockReplace = vi.fn();
const mockGetAccessToken = vi.fn();
const mockUseUser = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ replace: mockReplace }),
}));

vi.mock("@/lib/auth", () => ({
  getAccessToken: () => mockGetAccessToken(),
  clearTokens: vi.fn(),
}));

vi.mock("@/lib/UserContext", () => ({
  useUser: () => mockUseUser(),
}));

vi.mock("@/lib/i18n", () => ({
  useI18n: () => ({ t: (key: string) => key }),
}));

vi.mock("@/components/LanguageSelector", () => ({
  LanguageSelector: () => <div data-testid="language-selector">EN</div>,
}));

vi.mock("@/lib/api", () => ({
  api: { logout: vi.fn(() => Promise.resolve()) },
}));

describe("Shell auth redirect", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockGetAccessToken.mockReturnValue(null);
    mockUseUser.mockReturnValue({ user: null, loading: false });
  });

  it("redirects unauthenticated user to home when on protected route", () => {
    render(<Shell><div>Protected content</div></Shell>);
    expect(mockReplace).toHaveBeenCalledWith("/");
  });

  it("shows redirect state when unauthenticated on protected route", () => {
    render(<Shell><div>Protected content</div></Shell>);
    const els = screen.getAllByText("common.redirecting");
    expect(els.length).toBeGreaterThan(0);
  });
});

describe("Shell authenticated user", () => {
  beforeEach(() => {
    mockReplace.mockClear();
    mockGetAccessToken.mockReturnValue("fake-token");
    mockUseUser.mockReturnValue({
      user: {
        id: "1",
        username: "testuser",
        email: "a@b.com",
        profile_name: "",
        credits_balance: 100,
        paid_access: false,
        is_admin: false,
      },
      loading: false,
      refetch: async () => {},
    });
  });

  it("renders content when user is authenticated", () => {
    render(<Shell><div data-testid="protected-content">Dashboard</div></Shell>);
    expect(screen.getByTestId("protected-content")).toHaveTextContent("Dashboard");
    expect(mockReplace).not.toHaveBeenCalled();
  });
});
