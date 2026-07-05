# -- desktop file --------------------------------------------------------
desktop_file = i18n.merge_file(
  input: 'org.birdie.Birdie.desktop.in',
  output: 'org.birdie.Birdie.desktop',
  type: 'desktop',
  po_dir: '..' / 'po',
  install: true,
  install_dir: datadir / 'applications',
)

desktop_validate = find_program('desktop-file-validate', required: false)
if desktop_validate.found()
  test('validate-desktop', desktop_validate,
    args: [desktop_file],
  )
endif

# -- AppStream metainfo --------------------------------------------------
metainfo_file = i18n.merge_file(
  input: 'org.birdie.Birdie.metainfo.xml.in',
  output: 'org.birdie.Birdie.metainfo.xml',
  po_dir: '..' / 'po',
  install: true,
  install_dir: datadir / 'metainfo',
)

appstream_util = find_program('appstreamcli', required: false)
if appstream_util.found()
  test('validate-metainfo', appstream_util,
    args: ['validate', '--no-net', '--explain', metainfo_file],
  )
endif

# -- GSettings schema ----------------------------------------------------
install_data('org.birdie.Birdie.gschema.xml',
  install_dir: datadir / 'glib-2.0' / 'schemas',
)

compile_schemas = find_program('glib-compile-schemas', required: false)
if compile_schemas.found()
  test('validate-gschema', compile_schemas,
    args: ['--strict', '--dry-run', meson.current_source_dir()],
  )
endif

# -- icon ----------------------------------------------------------------
install_data(
  'icons' / 'hicolor' / 'scalable' / 'apps' / 'org.birdie.Birdie.svg',
  install_dir: datadir / 'icons' / 'hicolor' / 'scalable' / 'apps',
)
