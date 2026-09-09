async (page) => {
  await page.evaluate(async () => {
    document.querySelectorAll("dialog[open]").forEach(dialog => dialog.close());
    await loadPayload({ shapes: [{ type: 1048677, color: [40, 150, 210, 255], data: [10, 20, 0.5, 0.5, 0, 0, 0] }] });
    canvas.setActiveObject(vinylObjects()[0]);
    updateSelectionPanel();
  });
  const snapshot = () => page.evaluate(() => JSON.stringify(vinylObjects().map(object => objectToShape(object, { includeEditorMeta: true }))));
  const before = await snapshot();
  const keys = ["Delete", "Backspace", "Control+z", "Control+y", "Control+d", "Control+v", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "t", "s"];
  for (const kind of ["name", "confirmation", "message"]) {
    await page.evaluate(kind => {
      if (kind === "name") requestTextInput("Audit", "Name", "Keep this");
      else if (kind === "confirmation") requestConfirmation("Audit", "Keep this");
      else showEditorMessage("Audit", "Keep this");
    }, kind);
    const selector = kind === "name" ? "#textPromptCancel" : kind === "confirmation" ? "#confirmationDialogCancel" : "#messageDialogClose";
    await page.locator(selector).focus();
    for (const key of keys) await page.keyboard.press(key);
    if (await snapshot() !== before) throw new Error(`${kind} dialog allowed canvas edits`);
    await page.locator(selector).focus();
    await page.keyboard.press("Enter");
    await page.waitForFunction(() => !document.querySelector("dialog[open]"));
  }
  await page.locator("body").click({ position: { x: 5, y: 5 } });
  await page.keyboard.press("Delete");
  if (await page.evaluate(() => vinylObjects().length) !== 0) throw new Error("Canvas shortcuts did not resume after closing dialogs");
  return { dialogTypes: 3, blockedKeysPerDialog: keys.length, focusedButtonEnter: true, canvasShortcutsResume: true };
}
