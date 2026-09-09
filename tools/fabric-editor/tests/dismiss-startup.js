async (page) => {
  await page.evaluate(async () => {
    localStorage.setItem("kloudyFabricStartupHelpConfirmed", "true");
    KfpsEditorPreferences.setItem("kloudyFabricProjectSharingAcknowledged", "1");
    await KfpsEditorPreferences.flush();
    document.querySelectorAll("dialog[open]").forEach((dialog) => dialog.close());
  });
}
