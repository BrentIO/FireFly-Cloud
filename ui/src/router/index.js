import { createRouter, createWebHistory } from 'vue-router'
import LoginView from '../views/LoginView.vue'
import FirmwareView from '../views/FirmwareView.vue'

const routes = [
  {
    path: '/',
    redirect: '/login',
  },
  {
    path: '/login',
    name: 'login',
    component: LoginView,
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
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const isAuthenticated = !!sessionStorage.getItem('firefly_authenticated')

  if (!to.meta.public && !isAuthenticated) {
    next('/login')
  } else if (to.path === '/login' && isAuthenticated) {
    next('/firmware')
  } else {
    next()
  }
})

export default router
