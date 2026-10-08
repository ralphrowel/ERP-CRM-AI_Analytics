import { api } from './client'

export interface Department {
  id: number
  code: string
  name: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Employee {
  id: number
  employee_no: string
  first_name: string
  last_name: string
  email?: string | null
  phone?: string | null
  department_id: number
  job_title?: string | null
  manager_id?: number | null
  user_id?: number | null
  hire_date: string
  termination_date?: string | null
  is_active: boolean
  version: number
  created_at: string
  updated_at: string
}

export interface PaginatedEmployees {
  items: Employee[]
  total: number
  page: number
  page_size: number
}

export interface EmployeeCreatePayload {
  first_name: string
  last_name: string
  email?: string
  phone?: string
  department_id: number
  job_title?: string
  manager_id?: number | null
  user_id?: number | null
  hire_date: string
  termination_date?: string | null
}

export interface EmployeeUpdatePayload {
  first_name?: string
  last_name?: string
  email?: string
  phone?: string
  department_id?: number
  job_title?: string
  manager_id?: number | null
  user_id?: number | null
  hire_date?: string
  termination_date?: string | null
  is_active?: boolean
  version: number
}

export const employeesApi = {
  list: (params: { page?: number; page_size?: number; department_id?: number } = {}) => {
    const query = new URLSearchParams()
    if (params.page) query.set('page', params.page.toString())
    if (params.page_size) query.set('page_size', params.page_size.toString())
    if (params.department_id) query.set('department_id', params.department_id.toString())
    return api.get<PaginatedEmployees>(`/api/v1/employees?${query.toString()}`)
  },
  get: (id: number) => api.get<Employee>(`/api/v1/employees/${id}`),
  create: (data: EmployeeCreatePayload) => api.post<Employee>('/api/v1/employees', data),
  update: (id: number, data: EmployeeUpdatePayload) => api.patch<Employee>(`/api/v1/employees/${id}`, data),
  deactivate: (id: number) => api.post<Employee>(`/api/v1/employees/${id}/deactivate`),

  listDepartments: () => api.get<Department[]>('/api/v1/departments'),
  createDepartment: (code: string, name: string) =>
    api.post<Department>('/api/v1/departments', { code, name }),
}
