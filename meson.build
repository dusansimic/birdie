project('birdie',
  version: '0.1.0',
  meson_version: '>= 0.62.0',
  license: 'GPL-3.0-or-later',
)

python = import('python')
gnome = import('gnome')
i18n = import('i18n')

py = python.find_installation('python3', modules: ['gi', 'grpc'])

app_id = 'me.dusansimic.Birdie'

# Installation paths.
prefix = get_option('prefix')
bindir = get_option('bindir')
datadir = get_option('datadir')
pkgdatadir = datadir / meson.project_name()
# Python package root (…/site-packages or a private dir); we install the
# `birdie` package under the module install path.
moduledir = py.get_install_dir() / 'birdie'

subdir('data')
subdir('src')
subdir('po')

gnome.post_install(
  glib_compile_schemas: true,
  gtk_update_icon_cache: true,
  update_desktop_database: true,
)
