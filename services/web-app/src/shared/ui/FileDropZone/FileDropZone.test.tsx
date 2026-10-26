import { createRef } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FileDropZone, type FileDropZoneHandle } from "./FileDropZone";

const props = {
  accept: ".bundle",
  title: "Перетащи файл или",
  action: "выбери",
  activeTitle: "Отпусти файл",
  inputLabel: "Файл",
  testId: "zone",
  inputTestId: "input",
};

describe("FileDropZone", () => {
  afterEach(cleanup);

  it("отдаёт файл, выбранный через окно или брошенный на область", async () => {
    const onFile = vi.fn();
    render(<FileDropZone {...props} onFile={onFile} />);
    const user = userEvent.setup({ applyAccept: false });
    const picked = new File(["x"], "a.bundle");
    await user.upload(screen.getByTestId("input"), picked);
    expect(onFile).toHaveBeenLastCalledWith(picked);

    const dropped = new File(["y"], "b.bundle");
    fireEvent.drop(screen.getByTestId("zone"), {
      dataTransfer: { files: [dropped] },
    });
    expect(onFile).toHaveBeenLastCalledWith(dropped);
  });

  it("сообщает о неподходящем файле и не передаёт его", () => {
    const onFile = vi.fn();
    const onReject = vi.fn();
    render(
      <FileDropZone
        {...props}
        onFile={onFile}
        onReject={onReject}
        isAcceptable={(file) => file.name.endsWith(".bundle")}
      />,
    );
    const wrong = new File(["x"], "a.txt");
    fireEvent.drop(screen.getByTestId("zone"), {
      dataTransfer: { files: [wrong] },
    });
    expect(onReject).toHaveBeenCalledWith(wrong);
    expect(onFile).not.toHaveBeenCalled();
  });

  it("меняет подпись, пока файл над областью", () => {
    render(<FileDropZone {...props} onFile={vi.fn()} />);
    const zone = screen.getByTestId("zone");
    expect(zone).toHaveTextContent("Перетащи файл или выбери");
    fireEvent.dragOver(zone);
    expect(zone).toHaveTextContent("Отпусти файл");
    fireEvent.dragLeave(zone);
    expect(zone).toHaveTextContent("Перетащи файл или выбери");
  });

  it("открывает окно выбора с клавиатуры и через open()", async () => {
    const ref = createRef<FileDropZoneHandle>();
    render(<FileDropZone {...props} ref={ref} onFile={vi.fn()} />);
    const input = screen.getByTestId("input");
    const click = vi.spyOn(input, "click");
    const user = userEvent.setup();
    screen.getByTestId("zone").focus();
    await user.keyboard("{Enter}");
    expect(click).toHaveBeenCalledTimes(1);
    ref.current?.open();
    expect(click).toHaveBeenCalledTimes(2);
  });

  it("без рамки остаётся только input, а open() работает", () => {
    const ref = createRef<FileDropZoneHandle>();
    render(
      <FileDropZone {...props} ref={ref} showZone={false} onFile={vi.fn()} />,
    );
    expect(screen.queryByTestId("zone")).toBeNull();
    const click = vi.spyOn(screen.getByTestId("input"), "click");
    ref.current?.open();
    expect(click).toHaveBeenCalledTimes(1);
  });

  it("недоступная область ничего не принимает", () => {
    const onFile = vi.fn();
    render(<FileDropZone {...props} disabled onFile={onFile} />);
    const zone = screen.getByTestId("zone");
    expect(zone).toHaveAttribute("aria-disabled", "true");
    fireEvent.drop(zone, {
      dataTransfer: { files: [new File(["x"], "a.bundle")] },
    });
    expect(onFile).not.toHaveBeenCalled();
  });
});
