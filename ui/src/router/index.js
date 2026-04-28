import { createRouter, createWebHistory } from 'vue-router'
import LoginView      from '../views/LoginView.vue'
import CallbackView   from '../views/CallbackView.vue'
import FirmwareView   from '../views/FirmwareView.vue'
import UsersView      from '../views/UsersView.vue'
import AppConfigView  from '../views/AppConfigView.vue'
import DevicesView    from '../views/DevicesView.vue'
import { useAuth }    from '../composables/useAuth.js'

const routes = [
  {
    path: '/',
    redirect: '/firmware',
  },
  {
    path: '/login',
    name: 'login',
    component: LoginView,
    meta: { public: true },
  },
  {
    path: '/callback',
    name: 'callback',
    component: CallbackView,
    meta: { public: true },
  },
  {
    path: '/firmware',
    name: 'firmware',
    component: FirmwareView,
  },
  {
    path: '/firmware/:zip_name',
    name: 'firmware-detail',
    component: FirmwareView,
  },
  {
    path: '/users',
    name: 'users',
    component: UsersView,
  },
  {
    path: '/appconfig',
    name: 'appconfig',
    component: AppConfigView,
  },
  {
    path: '/devices',
    name: 'devices',
    component: DevicesView,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  if (to.meta.public) return true

  const auth = useAuth()
  const ok   = await auth.ensureAuthenticated()

  if (!ok) return '/login'
  return true
})

export default router
