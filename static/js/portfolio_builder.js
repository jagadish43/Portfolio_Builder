(() => {
  const form = document.querySelector("[data-portfolio-form]");
  if (!form) return;

  const portfolioIdMatch = form.getAttribute("action")?.match(/\/portfolios\/(\d+)\/edit/);
  const portfolioId = portfolioIdMatch ? portfolioIdMatch[1] : null;
  const educationJsonInput = form.querySelector("[data-education-json]");
  const skillsJsonInput = form.querySelector("[data-skills-json]");
  const educationTextInput = form.querySelector("[data-education-text]");
  const skillsTextInput = form.querySelector("[data-skills-text]");

  const educationTypeOptions = [
    "School",
    "PUC / Intermediate",
    "Diploma",
    "Degree",
    "Masters",
    "PhD",
    "Certification Program",
    "Bootcamp",
    "Custom",
  ];
  const skillCategoryOptions = [
    "Languages",
    "Frameworks",
    "Frontend",
    "Backend",
    "Databases",
    "Tools",
    "Cloud",
    "DevOps",
    "Testing",
    "AI/ML",
    "Libraries",
    "Platforms",
  ];

  function show(level, message) {
    if (window.showToast) window.showToast(level, message);
  }

  function csrfHeaders() {
    return {
      "Content-Type": "application/json",
      "X-CSRF-Token": window.csrfToken || "",
    };
  }

  function parseInitialJson(node) {
    try {
      return JSON.parse(node?.dataset.initial || "[]");
    } catch {
      return [];
    }
  }

  const sectionList = document.getElementById("section-order-list");
  if (sectionList && window.Sortable) {
    new window.Sortable(sectionList, {
      animation: 150,
      ghostClass: "opacity-50",
      onEnd() {
        sectionList.querySelectorAll("[data-section-item]").forEach((item) => {
          const input = item.querySelector('input[name="section_order"]');
          if (input) input.value = item.dataset.sectionItem || "";
        });
      },
    });
  }

  const preview = document.querySelector("[data-live-preview]");
  const previewName = document.querySelector("[data-preview-name]");
  const previewTitle = document.querySelector("[data-preview-title]");
  const previewBio = document.querySelector("[data-preview-bio]");
  const previewTemplate = document.querySelector("[data-preview-template]");

  function syncPreview() {
    if (!preview) return;
    const getValue = (name) => form.querySelector(`[name="${name}"]`)?.value || "";
    const mode = form.querySelector('[name="mode"]:checked')?.value || "light";
    const primary = getValue("primary_color");
    const accent = getValue("accent_color");
    const background = getValue("background_color");
    const surface = getValue("surface_color");
    const text = getValue("text_color");
    const font = getValue("font_family");
    preview.style.background = mode === "dark" ? "#0f172a" : background;
    preview.style.color = mode === "dark" ? "#f8fafc" : text;
    preview.style.fontFamily = `${font}, sans-serif`;
    const inner = preview.firstElementChild;
    if (inner) {
      inner.style.background = mode === "dark" ? "#111827" : surface;
      inner.style.borderTop = `6px solid ${primary}`;
      inner.style.boxShadow = `inset 0 0 0 1px ${accent}33`;
    }
    if (previewName) previewName.textContent = getValue("full_name") || "Your Name";
    if (previewTitle) previewTitle.textContent = getValue("title_tagline") || "Portfolio headline";
    if (previewBio) previewBio.textContent = getValue("bio") || "Your summary preview updates as you edit.";
    if (previewTemplate) previewTemplate.textContent = getValue("theme_slug") || "modern";
  }

  function defaultEducationEntry() {
    return {
      education_type: "Degree",
      custom_type: "",
      institution_name: "",
      course_name: "",
      university: "",
      specialization: "",
      start_year: "",
      end_year: "",
      score: "",
      location: "",
      description: "",
    };
  }

  function defaultSkillCategory() {
    return { category_name: "Languages", skills: [] };
  }

  const educationManager = form.querySelector("[data-education-manager]");
  const educationList = form.querySelector("[data-education-list]");
  let educationEntries = parseInitialJson(educationManager);
  if (!educationEntries.length) educationEntries = [defaultEducationEntry()];

  function educationSummary(entry) {
    return [entry.education_type === "Custom" ? entry.custom_type : entry.education_type, entry.course_name, entry.institution_name]
      .filter(Boolean)
      .join(" · ") || "New education";
  }

  function renderEducation() {
    if (!educationList) return;
    educationList.innerHTML = educationEntries.map((entry, index) => `
      <article class="rounded-3xl border border-slate-200 bg-slate-50 p-5" data-education-item data-index="${index}">
        <div class="flex items-center justify-between gap-4">
          <button class="min-w-0 text-left" type="button" data-toggle-education>
            <p class="truncate text-sm font-bold text-slate-900">${educationSummary(entry)}</p>
            <p class="mt-1 text-xs text-slate-500">Drag, expand, collapse, and reorder</p>
          </button>
          <div class="flex items-center gap-3">
            <span class="cursor-grab text-slate-400">⋮⋮</span>
            <button class="text-sm font-semibold text-rose-600" type="button" data-remove-education>Remove</button>
          </div>
        </div>
        <div class="mt-5 grid gap-4 md:grid-cols-2" data-education-body ${index > 0 ? "hidden" : ""}>
          <label class="block">
            <span class="mb-2 block text-sm font-semibold text-slate-700">Education type *</span>
            <select class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" data-education-field="education_type">
              ${educationTypeOptions.map((option) => `<option value="${option}" ${entry.education_type === option ? "selected" : ""}>${option}</option>`).join("")}
            </select>
          </label>
          <label class="block ${entry.education_type === "Custom" ? "" : "hidden"}" data-custom-type-wrap>
            <span class="mb-2 block text-sm font-semibold text-slate-700">Custom type *</span>
            <input class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" type="text" value="${entry.custom_type || ""}" data-education-field="custom_type" />
          </label>
          <label class="block">
            <span class="mb-2 block text-sm font-semibold text-slate-700">Institution name *</span>
            <input class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" type="text" value="${entry.institution_name || ""}" data-education-field="institution_name" />
          </label>
          <label class="block">
            <span class="mb-2 block text-sm font-semibold text-slate-700">Degree / course *</span>
            <input class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" type="text" value="${entry.course_name || ""}" data-education-field="course_name" />
          </label>
          <label class="block">
            <span class="mb-2 block text-sm font-semibold text-slate-700">Board / university</span>
            <input class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" type="text" value="${entry.university || ""}" data-education-field="university" />
          </label>
          <label class="block">
            <span class="mb-2 block text-sm font-semibold text-slate-700">Specialization</span>
            <input class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" type="text" value="${entry.specialization || ""}" data-education-field="specialization" />
          </label>
          <label class="block">
            <span class="mb-2 block text-sm font-semibold text-slate-700">Start year</span>
            <input class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" type="text" value="${entry.start_year || ""}" data-education-field="start_year" />
          </label>
          <label class="block">
            <span class="mb-2 block text-sm font-semibold text-slate-700">End year</span>
            <input class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" type="text" value="${entry.end_year || ""}" data-education-field="end_year" />
          </label>
          <label class="block">
            <span class="mb-2 block text-sm font-semibold text-slate-700">CGPA / percentage</span>
            <input class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" type="text" value="${entry.score || ""}" data-education-field="score" />
          </label>
          <label class="block">
            <span class="mb-2 block text-sm font-semibold text-slate-700">Location</span>
            <input class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" type="text" value="${entry.location || ""}" data-education-field="location" />
          </label>
          <label class="block md:col-span-2">
            <span class="mb-2 block text-sm font-semibold text-slate-700">Description</span>
            <textarea class="min-h-24 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" data-education-field="description">${entry.description || ""}</textarea>
          </label>
        </div>
      </article>
    `).join("");

    if (window.Sortable && educationList.children.length > 1) {
      if (educationList._sortable) educationList._sortable.destroy();
      educationList._sortable = new window.Sortable(educationList, {
        animation: 150,
        handle: ".cursor-grab",
        onEnd() {
          educationEntries = [...educationList.querySelectorAll("[data-education-item]")].map((item) => educationEntries[Number(item.dataset.index)]);
          renderEducation();
        },
      });
    }
    syncStructuredFields();
  }

  const skillsManager = form.querySelector("[data-skills-manager]");
  const skillCategoryList = form.querySelector("[data-skill-category-list]");
  let skillCategories = parseInitialJson(skillsManager);
  if (!skillCategories.length) skillCategories = [defaultSkillCategory()];

  function renderSkillCategories() {
    if (!skillCategoryList) return;
    skillCategoryList.innerHTML = skillCategories.map((category, index) => `
      <article class="rounded-3xl border border-slate-200 bg-slate-50 p-5" data-skill-category data-index="${index}">
        <div class="flex items-center justify-between gap-4">
          <div class="flex min-w-0 items-center gap-3">
            <span class="cursor-grab text-slate-400">⋮⋮</span>
            <input class="min-w-0 flex-1 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-900" list="skill-category-options" value="${category.category_name || ""}" data-skill-category-name />
          </div>
          <button class="text-sm font-semibold text-rose-600" type="button" data-remove-skill-category>Remove</button>
        </div>
        <div class="mt-4 flex flex-wrap gap-2" data-skill-chip-list>
          ${(category.skills || []).map((skill, skillIndex) => `
            <span class="inline-flex items-center gap-2 rounded-full bg-white px-3 py-2 text-sm font-semibold text-slate-700" data-skill-chip data-skill-index="${skillIndex}">
              <span class="cursor-grab text-slate-400">⋮</span>
              ${skill}
              <button class="text-slate-400 hover:text-rose-600" type="button" data-remove-skill>×</button>
            </span>
          `).join("")}
        </div>
        <div class="mt-4 flex gap-3">
          <input class="min-w-0 flex-1 rounded-2xl border border-slate-200 bg-white px-4 py-3" type="text" placeholder="Add skill and press Enter" data-skill-input />
          <button class="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700" type="button" data-add-skill>Add skill</button>
        </div>
      </article>
    `).join("") + `
      <datalist id="skill-category-options">
        ${skillCategoryOptions.map((option) => `<option value="${option}"></option>`).join("")}
      </datalist>
    `;

    if (window.Sortable && skillCategoryList.children.length > 1) {
      if (skillCategoryList._sortable) skillCategoryList._sortable.destroy();
      skillCategoryList._sortable = new window.Sortable(skillCategoryList, {
        animation: 150,
        handle: ".cursor-grab",
        onEnd() {
          skillCategories = [...skillCategoryList.querySelectorAll("[data-skill-category]")].map((item) => skillCategories[Number(item.dataset.index)]);
          renderSkillCategories();
        },
      });
    }

    skillCategoryList.querySelectorAll("[data-skill-chip-list]").forEach((chipList, categoryIndex) => {
      if (window.Sortable) {
        new window.Sortable(chipList, {
          animation: 150,
          handle: ".cursor-grab",
          onEnd() {
            const reordered = [...chipList.querySelectorAll("[data-skill-chip]")].map((chip) => {
              const skillIndex = Number(chip.dataset.skillIndex);
              return skillCategories[categoryIndex].skills[skillIndex];
            });
            skillCategories[categoryIndex].skills = reordered;
            renderSkillCategories();
          },
        });
      }
    });
    syncStructuredFields();
  }

  function syncStructuredFields() {
    if (educationJsonInput) educationJsonInput.value = JSON.stringify(educationEntries);
    if (skillsJsonInput) skillsJsonInput.value = JSON.stringify(skillCategories);
    if (educationTextInput) {
      educationTextInput.value = educationEntries.map((entry) => {
        const type = entry.education_type === "Custom" ? entry.custom_type : entry.education_type;
        return [type, entry.course_name, entry.institution_name].filter(Boolean).join(" - ");
      }).filter(Boolean).join("\n");
    }
    if (skillsTextInput) {
      skillsTextInput.value = skillCategories.flatMap((category) => category.skills || []).join(", ");
    }
  }

  renderEducation();
  renderSkillCategories();

  function buildItem(type) {
    const templates = {
      projects: `
        <article class="rounded-3xl border border-slate-200 bg-slate-50 p-5" data-repeater-item="projects">
          <div class="grid gap-4 md:grid-cols-2">
            <label class="block"><span class="mb-2 block text-sm font-semibold text-slate-700">Title *</span><input class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" type="text" name="project_title" /></label>
            <label class="block"><span class="mb-2 block text-sm font-semibold text-slate-700">Live URL</span><input class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" type="url" name="project_live_url" /></label>
            <label class="block"><span class="mb-2 block text-sm font-semibold text-slate-700">GitHub URL</span><input class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" type="url" name="project_github_url" /></label>
            <label class="block"><span class="mb-2 block text-sm font-semibold text-slate-700">Tech stack</span><input class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" type="text" name="project_tech_stack" /></label>
            <label class="block md:col-span-2"><span class="mb-2 block text-sm font-semibold text-slate-700">Description *</span><textarea class="min-h-28 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" name="project_description" data-ai-target="project_description"></textarea></label>
          </div>
          <div class="mt-4 flex justify-end"><button class="text-sm font-semibold text-rose-600" type="button" data-remove-item="projects">Remove</button></div>
        </article>`,
      experience: `
        <article class="rounded-3xl border border-slate-200 bg-slate-50 p-5" data-repeater-item="experience">
          <div class="grid gap-4 md:grid-cols-2">
            <label class="block"><span class="mb-2 block text-sm font-semibold text-slate-700">Role *</span><input class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" type="text" name="experience_role" /></label>
            <label class="block"><span class="mb-2 block text-sm font-semibold text-slate-700">Company *</span><input class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" type="text" name="experience_company" /></label>
            <label class="block md:col-span-2"><span class="mb-2 block text-sm font-semibold text-slate-700">Duration</span><input class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" type="text" name="experience_duration" /></label>
            <label class="block md:col-span-2"><span class="mb-2 block text-sm font-semibold text-slate-700">Description *</span><textarea class="min-h-28 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" name="experience_description" data-ai-target="experience_description"></textarea></label>
          </div>
          <div class="mt-4 flex justify-end"><button class="text-sm font-semibold text-rose-600" type="button" data-remove-item="experience">Remove</button></div>
        </article>`,
      certificates: `
        <article class="rounded-3xl border border-slate-200 bg-slate-50 p-5" data-repeater-item="certificates">
          <div class="grid gap-4 md:grid-cols-2">
            <label class="block"><span class="mb-2 block text-sm font-semibold text-slate-700">Name *</span><input class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" type="text" name="certificate_name" /></label>
            <label class="block"><span class="mb-2 block text-sm font-semibold text-slate-700">Issuer *</span><input class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" type="text" name="certificate_issuer" /></label>
            <label class="block"><span class="mb-2 block text-sm font-semibold text-slate-700">Year</span><input class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" type="text" name="certificate_year" /></label>
            <label class="block"><span class="mb-2 block text-sm font-semibold text-slate-700">URL</span><input class="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3" type="url" name="certificate_url" /></label>
          </div>
          <div class="mt-4 flex justify-end"><button class="text-sm font-semibold text-rose-600" type="button" data-remove-item="certificates">Remove</button></div>
        </article>`,
    };
    return templates[type] || "";
  }

  form.querySelectorAll("input, textarea, select").forEach((field) => {
    field.addEventListener("input", syncPreview);
    field.addEventListener("change", syncPreview);
  });
  syncPreview();

  form.addEventListener("input", (event) => {
    const educationField = event.target.closest("[data-education-field]");
    const educationCard = event.target.closest("[data-education-item]");
    if (educationField && educationCard) {
      const index = Number(educationCard.dataset.index);
      educationEntries[index][educationField.dataset.educationField] = event.target.value;
      if (educationField.dataset.educationField === "education_type") renderEducation();
      syncStructuredFields();
      return;
    }

    const categoryNameInput = event.target.closest("[data-skill-category-name]");
    const categoryCard = event.target.closest("[data-skill-category]");
    if (categoryNameInput && categoryCard) {
      const index = Number(categoryCard.dataset.index);
      skillCategories[index].category_name = categoryNameInput.value;
      syncStructuredFields();
    }
  });

  form.addEventListener("keydown", (event) => {
    const skillInput = event.target.closest("[data-skill-input]");
    if (skillInput && event.key === "Enter") {
      event.preventDefault();
      skillInput.closest("[data-skill-category]")?.querySelector("[data-add-skill]")?.click();
    }
  });

  form.addEventListener("click", async (event) => {
    const addEducationButton = event.target.closest("[data-add-education]");
    if (addEducationButton) {
      educationEntries.push(defaultEducationEntry());
      renderEducation();
      return;
    }

    const toggleEducationButton = event.target.closest("[data-toggle-education]");
    if (toggleEducationButton) {
      toggleEducationButton.closest("[data-education-item]")?.querySelector("[data-education-body]")?.toggleAttribute("hidden");
      return;
    }

    const removeEducationButton = event.target.closest("[data-remove-education]");
    if (removeEducationButton) {
      const card = removeEducationButton.closest("[data-education-item]");
      educationEntries.splice(Number(card.dataset.index), 1);
      if (!educationEntries.length) educationEntries = [defaultEducationEntry()];
      renderEducation();
      return;
    }

    const addSkillCategoryButton = event.target.closest("[data-add-skill-category]");
    if (addSkillCategoryButton) {
      skillCategories.push(defaultSkillCategory());
      renderSkillCategories();
      return;
    }

    const removeSkillCategoryButton = event.target.closest("[data-remove-skill-category]");
    if (removeSkillCategoryButton) {
      const card = removeSkillCategoryButton.closest("[data-skill-category]");
      skillCategories.splice(Number(card.dataset.index), 1);
      if (!skillCategories.length) skillCategories = [defaultSkillCategory()];
      renderSkillCategories();
      return;
    }

    const addSkillButton = event.target.closest("[data-add-skill]");
    if (addSkillButton) {
      const card = addSkillButton.closest("[data-skill-category]");
      const index = Number(card.dataset.index);
      const input = card.querySelector("[data-skill-input]");
      const value = input.value.trim();
      if (!value) return;
      const duplicates = new Set(skillCategories[index].skills.map((skill) => skill.toLowerCase()));
      if (duplicates.has(value.toLowerCase())) {
        show("warning", "Duplicate skill ignored.");
        input.value = "";
        return;
      }
      skillCategories[index].skills.push(value);
      input.value = "";
      renderSkillCategories();
      return;
    }

    const removeSkillButton = event.target.closest("[data-remove-skill]");
    if (removeSkillButton) {
      const card = removeSkillButton.closest("[data-skill-category]");
      const categoryIndex = Number(card.dataset.index);
      const chip = removeSkillButton.closest("[data-skill-chip]");
      skillCategories[categoryIndex].skills.splice(Number(chip.dataset.skillIndex), 1);
      renderSkillCategories();
      return;
    }

    const addButton = event.target.closest("[data-add-item]");
    if (addButton) {
      const listName = addButton.dataset.addItem;
      const list = form.querySelector(`[data-repeater-list="${listName}"]`);
      if (list) list.insertAdjacentHTML("beforeend", buildItem(listName));
      return;
    }

    const removeButton = event.target.closest("[data-remove-item]");
    if (removeButton) {
      removeButton.closest("[data-repeater-item]")?.remove();
      return;
    }

    const aiButton = event.target.closest("[data-ai-enhance]");
    if (aiButton) {
      const targetKey = aiButton.dataset.target;
      let target = aiButton.closest("section, article, label")?.querySelector(`[data-ai-target="${targetKey}"]`) || form.querySelector(`[data-ai-target="${targetKey}"]`);
      if (!(target instanceof HTMLTextAreaElement || target instanceof HTMLInputElement)) return;
      const originalLabel = aiButton.textContent;
      aiButton.setAttribute("disabled", "disabled");
      aiButton.textContent = "Enhancing...";
      try {
        const response = await fetch("/api/ai/enhance", {
          method: "POST",
          headers: csrfHeaders(),
          body: JSON.stringify({
            content_type: aiButton.dataset.aiEnhance,
            text: target.value || skillsTextInput?.value || "",
            concise: false,
          }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "AI enhancement failed.");
        if (targetKey === "skills_text") {
          const category = skillCategories[0] || defaultSkillCategory();
          category.skills = (data.enhanced_text || "").split(",").map((item) => item.trim()).filter(Boolean);
          skillCategories[0] = category;
          renderSkillCategories();
        } else {
          target.value = data.enhanced_text || target.value;
        }
        syncStructuredFields();
        syncPreview();
        show("success", data.used_fallback ? "Used fallback enhancement." : "Content enhanced.");
      } catch (error) {
        show("error", error.message || "AI enhancement failed.");
      } finally {
        aiButton.removeAttribute("disabled");
        aiButton.textContent = originalLabel;
      }
      return;
    }

    const resumeButton = event.target.closest("[data-download-resume]");
    if (resumeButton && portfolioId) {
      window.location.href = `/api/portfolios/${portfolioId}/resume.pdf`;
      return;
    }

    const domainButton = event.target.closest("[data-connect-domain]");
    if (domainButton && portfolioId) {
      const domain = form.querySelector("[data-custom-domain]")?.value?.trim();
      if (!domain) return show("warning", "Enter a custom domain first.");
      const response = await fetch(`/api/portfolios/${portfolioId}/domains`, {
        method: "POST",
        headers: csrfHeaders(),
        body: JSON.stringify({ domain }),
      });
      const data = await response.json();
      if (!response.ok) return show("error", data.detail || "Domain connection failed.");
      show("success", `Domain saved. Add TXT value: ${data.verification_token}`);
      return;
    }

    const deployButton = event.target.closest("[data-deploy-portfolio]");
    if (deployButton && portfolioId) {
      const response = await fetch(`/api/portfolios/${portfolioId}/deployments`, {
        method: "POST",
        headers: csrfHeaders(),
        body: JSON.stringify({ production: true }),
      });
      const data = await response.json();
      if (!response.ok) return show("error", data.detail || "Deployment failed.");
      show("success", data.deployment_url ? `Deployment ready: ${data.deployment_url}` : "Deployment queued.");
      return;
    }

    const githubButton = event.target.closest("[data-github-import]");
    if (githubButton && portfolioId) {
      const username = form.querySelector("[data-github-username]")?.value?.trim();
      const repositories = (form.querySelector("[data-github-repos]")?.value || "").split(",").map((item) => item.trim()).filter(Boolean);
      if (!username || !repositories.length) return show("warning", "Enter a GitHub username and at least one repository.");
      const response = await fetch(`/api/portfolios/${portfolioId}/github-import`, {
        method: "POST",
        headers: csrfHeaders(),
        body: JSON.stringify({ username, repository_names: repositories }),
      });
      const data = await response.json();
      if (!response.ok) return show("error", data.detail || "GitHub import failed.");
      show("success", `Imported ${data.imported_count} repositories. Reloading form.`);
      window.location.reload();
      return;
    }

    const linkedinButton = event.target.closest("[data-linkedin-import]");
    if (linkedinButton && portfolioId) {
      const payload = {
        full_name: form.querySelector('[name="full_name"]')?.value || "",
        headline: form.querySelector('[name="title_tagline"]')?.value || "",
        bio: form.querySelector('[name="bio"]')?.value || "",
        skills: skillCategories.flatMap((category) => category.skills || []),
        experiences: [],
        education_text: educationTextInput?.value || "",
      };
      const response = await fetch(`/api/portfolios/${portfolioId}/linkedin-import`, {
        method: "POST",
        headers: csrfHeaders(),
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) return show("error", data.detail || "LinkedIn import failed.");
      show("success", "LinkedIn fallback import applied.");
    }
  });
})();
