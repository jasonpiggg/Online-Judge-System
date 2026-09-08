import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import {
  Link,
  MemoryRouter,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import {
  ActivityBar,
  ActivityProvider,
  TaskAction,
  TaskLink,
  useRegisterActivity,
} from "./Activity";
import { BackLink } from "./BackLink";
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
beforeEach(() => {
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  localStorage.clear();
  sessionStorage.clear();
});
function Page({ draft = false }: { draft?: boolean }) {
  const location = useLocation();
  useRegisterActivity({
    id: draft ? "draft:d1" : "problem:p1",
    kind: draft ? "draft" : "problem",
    title: draft ? "Draft" : "Problem",
    path: location.pathname + location.search,
  });
  return (
    <>
      <BackLink />
      <output aria-label="path">{location.pathname}</output>
      <TaskAction label="Edit" to="/authoring/drafts/d1" />
    </>
  );
}
function App() {
  return (
    <MemoryRouter initialEntries={["/problems"]}>
      <ActivityProvider userId="7">
        <Link to="/problems">Home</Link>
        <ActivityBar />
        <Routes>
          <Route
            path="/problems"
            element={<TaskLink to="/problems/p1">Open problem</TaskLink>}
          />
          <Route path="/problems/p1" element={<Page />} />
          <Route path="/authoring/drafts/d1" element={<Page draft />} />
        </Routes>
      </ActivityProvider>
    </MemoryRouter>
  );
}
it("clears active state at hubs and reuses a task through its history", async () => {
  render(<App />);
  fireEvent.click(screen.getByText("Open problem"));
  fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
  expect(await screen.findByLabelText("path")).toHaveTextContent(
    "/authoring/drafts/d1",
  );
  fireEvent.click(screen.getByText("Home"));
  expect(document.querySelector(".activity-tab.active")).toBeNull();
  fireEvent.click(screen.getByText("Open problem"));
  expect(await screen.findByLabelText("path")).toHaveTextContent(
    "/problems/p1",
  );
  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  expect(await screen.findByLabelText("path")).toHaveTextContent(
    "/authoring/drafts/d1",
  );
  expect(document.querySelectorAll(".activity-tab")).toHaveLength(1);
});
it("explicit new-tab action preserves the source and reuses an existing destination", async () => {
  render(<App />);
  fireEvent.click(screen.getByText("Open problem"));
  fireEvent.click(await screen.findByLabelText("Edit的打开方式"));
  fireEvent.click(screen.getByRole("button", { name: "在新标签页打开" }));
  expect(await screen.findByLabelText("path")).toHaveTextContent(
    "/authoring/drafts/d1",
  );
  expect(document.querySelectorAll(".activity-tab")).toHaveLength(2);
  fireEvent.click(screen.getByRole("button", { name: "Problem" }));
  fireEvent.click(screen.getByRole("button", { name: "Edit" }));
  expect(await screen.findByLabelText("path")).toHaveTextContent(
    "/authoring/drafts/d1",
  );
  expect(document.querySelectorAll(".activity-tab")).toHaveLength(2);
});

it("closing a background tab leaves the hub visible", async () => {
  render(<App />);
  fireEvent.click(screen.getByText("Open problem"));
  await screen.findByRole("button", { name: "关闭 Problem" });
  fireEvent.click(screen.getByText("Home"));
  fireEvent.click(screen.getByRole("button", { name: "关闭 Problem" }));
  expect(screen.getByText("Open problem")).toBeInTheDocument();
  expect(document.querySelectorAll(".activity-tab")).toHaveLength(0);
});
it("rejects persisted external routes", () => {
  localStorage.setItem("oj-activities-7", JSON.stringify({ version: 2, slots: [{
    id: "external", current: { id: "problem:p1", kind: "problem", title: "External", path: "//evil.example/problems/p1" }, backStack: [], touchedAt: 1,
  }] }));
  render(<App />);
  expect(screen.queryByText("External")).not.toBeInTheDocument();
});
